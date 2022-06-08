#  Copyright (c) 2022. Matteo Bettini
#  All rights reserved.
import math
from typing import Dict

import torch
from maps.simulator.core import Agent, World, Landmark, Sphere
from maps.simulator.scenario import BaseScenario
from maps.simulator.utils import Color
from torch import Tensor


class Scenario(BaseScenario):
    def make_world(self, batch_dim: int, device: torch.device, **kwargs):
        n_agents = kwargs.get("n_agents", 4)
        energy_coeff = kwargs.get("energy_coeff", 0.2)

        self.energy_coeff = energy_coeff

        # Make world
        world = World(batch_dim, device, x_semidim=1, y_semidim=1)
        # Add agents
        for i in range(n_agents):
            # Constraint: all agents have same action range and multiplier
            agent = Agent(name=f"agent {i}")
            world.add_agent(agent)
        # Add landmarks
        goal = Landmark(
            name=f"goal",
            collide=False,
            shape=Sphere(radius=0.05),
            color=Color.GREEN,
        )
        world.add_landmark(goal)

        return world

    def reset_world_at(self, env_index: int = None):
        for agent in self.world.agents:
            agent.set_pos(
                2
                * torch.rand(
                    self.world.dim_p, device=self.world.device, dtype=torch.float32
                )
                - 1,
                batch_index=env_index,
            )
        for landmark in self.world.landmarks:
            landmark.set_pos(
                2
                * torch.rand(
                    self.world.dim_p, device=self.world.device, dtype=torch.float32
                )
                - 1,
                batch_index=env_index,
            )

    def reward(self, agent: Agent):
        # pos_rew = -torch.min(
        #     torch.stack(
        #         [
        #             (a.state.pos - self.world.landmarks[0].state.pos)
        #             .square()
        #             .sum(-1)
        #             .sqrt()
        #             for a in self.world.agents
        #         ],
        #         dim=1,
        #     ),
        #     dim=-1,
        # )[0]
        #
        # # Scale by max possible distance, world is bounded between -1 and 1
        # self.pos_rew = pos_rew / math.sqrt(
        #     ((2 * self.world.x_semidim) ** 2) + ((2 * self.world.y_semidim) ** 2)
        # )
        #
        # assert torch.all(self.pos_rew <= 0) and torch.all(self.pos_rew >= -1)
        self._done = torch.any(
            torch.stack(
                [
                    torch.sqrt(
                        (a.state.pos - self.world.landmarks[0].state.pos)
                        .square()
                        .sum(-1)
                    )
                    < self.world.landmarks[0].shape.radius
                    for a in self.world.agents
                ],
                dim=1,
            ),
            dim=-1,
        )

        self.pos_rew = torch.zeros(self.world.batch_dim, device=self.world.device)
        self.pos_rew[self._done] = 1

        # Assumption: all agents have same action range and multiplier
        self.energy_rew = (
            self.energy_coeff
            * -torch.stack(
                [
                    torch.linalg.norm(a.action.u, dim=-1)
                    / math.sqrt(self.world.dim_p * ((a.u_range * a.u_multiplier) ** 2))
                    for a in self.world.agents
                ],
                dim=1,
            ).sum(-1)
            # / len(self.world.agents)
        )
        if self.energy_coeff != 0:
            assert torch.all((self.energy_rew / self.energy_coeff) <= 0) and torch.all(
                (self.energy_rew / self.energy_coeff) >= -1
            )

        rew = self.pos_rew + self.energy_rew

        return rew

    def observation(self, agent: Agent):
        return torch.cat(
            [
                agent.state.pos,
                agent.state.vel,
                agent.state.pos - self.world.landmarks[0].state.pos,
            ],
            dim=-1,
        )

    def info(self, agent: Agent) -> Dict[str, Tensor]:
        try:
            info = {"pos_rew": self.pos_rew, "energy_rew": self.energy_rew}
        except AttributeError:
            info = {}
        return info

    def done(self):
        return self._done