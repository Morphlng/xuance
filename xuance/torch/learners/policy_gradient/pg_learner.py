"""
Policy Gradient (PG)
Paper link: https://proceedings.neurips.cc/paper/2001/file/4b86abe48d358ecf194c56c69108433e-Paper.pdf
Implementation: Pytorch
"""
import torch
from torch import nn
from xuance.torch.learners import Learner
from argparse import Namespace


class PG_Learner(Learner):
    def __init__(self,
                 config: Namespace,
                 policy: nn.Module):
        super(PG_Learner, self).__init__(config, policy)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), self.config.learning_rate, eps=1e-5)
        self.scheduler = torch.optim.lr_scheduler.LinearLR(self.optimizer, start_factor=1.0, end_factor=0.0,
                                                           total_iters=self.config.running_steps)
        self.ent_coef = config.ent_coef

    def update(self, **samples):
        self.iterations += 1
        obs_batch = samples['obs']
        act_batch = torch.as_tensor(samples['actions'], device=self.device)
        ret_batch = torch.as_tensor(samples['returns'], device=self.device)
        _, a_dist, _ = self.policy(obs_batch)
        log_prob = a_dist.log_prob(act_batch)

        a_loss = -(ret_batch * log_prob).mean()
        e_loss = a_dist.entropy().mean()

        loss = a_loss - self.ent_coef * e_loss
        self.optimizer.zero_grad()
        loss.backward()
        if self.use_grad_clip:
            torch.nn.utils.clip_grad_norm_(self.policy.parameters(), self.grad_clip_norm)
        self.optimizer.step()
        if self.scheduler is not None:
            self.scheduler.step()

        # Logger
        lr = self.optimizer.state_dict()['param_groups'][0]['lr']

        info = {
            "actor-loss": a_loss.item(),
            "entropy": e_loss.item(),
            "learning_rate": lr
        }

        return info
