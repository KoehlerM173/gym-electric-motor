import gym
from gym_electric_motor.physical_systems.converters.finite_control_set import FiniteConverter

class FiniteOneQuadrantConverter(FiniteConverter):
    """
    Key:
        'Finite-1QC'

    Switching States / Actions:
        | 0: Transistor off.
        | 1: Transistor on.

    Action Space:
        Discrete(2)

    Output Voltages and Currents:
        | voltages: Box(0, 1, shape=(1,))
        | currents: Box(0, 1, shape=(1,))
    """

    action_space = gym.spaces.Discrete(2)
    
    current_space = gym.spaces.Box(0,1, shape=(1,))

    voltage_space = gym.spaces.Box(0,1, shape=(1,))

    def convert(self, t, i_out, u_sup):
        # Docstring in base class
        return [self._current_action * u_sup[0] if i_out[0] >= 0 else u_sup[0]]

    def i_sup(self, i_out):
        # Docstring in base class
        return i_out[0] if self._current_action == 1 else 0
