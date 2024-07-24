"""
Deep Deterministic Policy Gradient (DDPG)
Paper link: https://arxiv.org/pdf/1509.02971.pdf
Implementation: TensorFlow2
"""
from argparse import Namespace
from xuance.tensorflow import tf, tk, Module
from xuance.tensorflow.learners import Learner


class DDPG_Learner(Learner):
    def __init__(self,
                 config: Namespace,
                 policy: Module):
        super(DDPG_Learner, self).__init__(config, policy)
        if ("macOS" in self.os_name) and ("arm" in self.os_name):  # For macOS with Apple's M-series chips.
            self.optimizer = {'actor': tk.optimizers.legacy.Adam(config.actor_learning_rate),
                              'critic': tk.optimizers.legacy.Adam(config.critic_learning_rate)}

        else:
            self.optimizer = {'actor': tk.optimizers.Adam(config.actor_learning_rate),
                              'critic': tk.optimizers.Adam(config.critic_learning_rate)}
        self.tau = config.tau
        self.gamma = config.gamma

    @tf.function
    def learn_actor(self, obs_batch):
        with tf.GradientTape() as tape:
            policy_q = self.policy.Qpolicy(obs_batch)
            p_loss = -tf.reduce_mean(policy_q)
            gradients = tape.gradient(
                p_loss, self.policy.actor_representation.trainable_variables + self.policy.actor.trainable_variables)
            if self.use_grad_clip:
                self.optimizer['actor'].apply_gradients([
                    (tf.clip_by_norm(grad, self.grad_clip_norm), var)
                    for (grad, var) in zip(
                        gradients, self.policy.actor_representation.trainable_variables + self.policy.actor.trainable_variables)
                    if grad is not None
                ])
            else:
                self.optimizer['actor'].apply_gradients([(grad, var) for (grad, var) in zip(
                    gradients, self.policy.actor_representation.trainable_variables + self.policy.actor.trainable_variables)
                                                         if grad is not None])
        return p_loss

    @tf.function
    def learn_critic(self, obs_batch, act_batch, next_batch, rew_batch, ter_batch):
        with tf.GradientTape() as tape:
            action_q = self.policy.Qaction(obs_batch, act_batch)
            next_q = self.policy.Qtarget(next_batch)
            backup = rew_batch + (1 - ter_batch) * self.gamma * next_q
            y_true = tf.reshape(tf.stop_gradient(backup), [-1])
            y_pred = tf.reshape(action_q, [-1])
            q_loss = tk.losses.mean_squared_error(y_true, y_pred)
            gradients = tape.gradient(
                q_loss, self.policy.critic_representation.trainable_variables + self.policy.critic.trainable_variables)
            if self.use_grad_clip:
                self.optimizer['critic'].apply_gradients([
                    (tf.clip_by_norm(grad, self.grad_clip_norm), var)
                    for (grad, var) in zip(
                        gradients, self.policy.critic_representation.trainable_variables + self.policy.critic.trainable_variables)
                    if grad is not None
                ])
            else:
                self.optimizer['critic'].apply_gradients([
                    (grad, var)
                    for (grad, var) in zip(
                        gradients,
                        self.policy.critic_representation.trainable_variables + self.policy.critic.trainable_variables)
                    if grad is not None
                ])
        return q_loss, action_q

    def update(self, **samples):
        self.iterations += 1
        obs_batch = samples['obs']
        act_batch = samples['actions']
        next_batch = samples['obs_next']
        rew_batch = samples['rewards']
        ter_batch = samples['terminals']

        # critic update
        q_loss, action_q = self.learn_critic(obs_batch, act_batch, next_batch, rew_batch, ter_batch)

        # actor update
        p_loss = self.learn_actor(obs_batch)

        self.policy.soft_update(self.tau)

        info = {
            "Qloss": q_loss.numpy(),
            "Ploss": p_loss.numpy(),
            "Qvalue": tf.reduce_mean(action_q).numpy(),
        }

        return info
