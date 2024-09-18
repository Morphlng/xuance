"""
Deep Q-Network (DQN)
Paper link: https://www.nature.com/articles/nature14236
Implementation: Pytorch
"""
import os
import torch
from torch import nn
from argparse import Namespace
from xuance.torch.learners import Learner
from torch.nn.parallel import DistributedDataParallel


class DQN_Learner(Learner):
    def __init__(self,
                 config: Namespace,
                 policy: nn.Module):
        super(DQN_Learner, self).__init__(config, policy)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), self.config.learning_rate, eps=1e-5)
        self.scheduler = torch.optim.lr_scheduler.LinearLR(self.optimizer, start_factor=1.0, end_factor=0.0,
                                                           total_iters=self.config.running_steps)
        self.gamma = config.gamma
        self.sync_frequency = config.sync_frequency
        self.mse_loss = nn.MSELoss()
        self.one_hot = nn.functional.one_hot
        self.n_actions = self.policy.action_dim
        # parallel settings
        if self.use_ddp:
            self.device = config.rank
            self.policy = DistributedDataParallel(self.policy, find_unused_parameters=True,
                                                  device_ids=[self.config.rank])

    def update(self, **samples):
        self.iterations += 1
        obs_batch = torch.as_tensor(samples['obs'], device=self.device)
        act_batch = torch.as_tensor(samples['actions'], device=self.device)
        next_batch = torch.as_tensor(samples['obs_next'], device=self.device)
        rew_batch = torch.as_tensor(samples['rewards'], device=self.device)
        ter_batch = torch.as_tensor(samples['terminals'], device=self.device)

        _, _, evalQ = self.policy(obs_batch)
        _, _, targetQ = self.policy.module.target(next_batch) if self.use_ddp else self.policy.target(next_batch)
        targetQ = targetQ.max(dim=-1).values
        targetQ = rew_batch + self.gamma * (1 - ter_batch) * targetQ
        predictQ = (evalQ * self.one_hot(act_batch.long(), evalQ.shape[1])).sum(dim=-1)

        loss = self.mse_loss(predictQ, targetQ)
        self.optimizer.zero_grad()
        loss.backward()
        if self.use_grad_clip:
            torch.nn.utils.clip_grad_norm_(self.policy.parameters(), self.grad_clip_norm)
        self.optimizer.step()
        if self.scheduler is not None:
            self.scheduler.step()

        # hard update for target network
        if self.iterations % self.sync_frequency == 0:
            if self.use_ddp:
                self.policy.module.copy_target()
            else:
                self.policy.copy_target()
        lr = self.optimizer.state_dict()['param_groups'][0]['lr']

        info = {
            "Qloss": loss.item(),
            "predictQ": predictQ.mean().item(),
            "learning_rate": lr,
        }

        return info
