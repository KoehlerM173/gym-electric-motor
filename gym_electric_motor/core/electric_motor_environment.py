import gym
import gym.spaces
import numpy as np


import gym_electric_motor as gem


class ElectricMotorEnvironment(gym.Env):
    """
    Description:
        The central instance connecting all components of a gym-electric-motor environment.

    Components:

        Physical System:
            Containing the physical structure and simulation of the drive system as well as information about the
            technical limits and nominal values. Needs to be a subclass of *PhysicalSystem*

        Reference Generator:
            Generation of the reference for the motor to follow. Needs to be a subclass of *ReferenceGenerator*

        Reward Function:
            Calculation of the reward based on the state of the physical system and the generated reference
            and observation if the motor state is within the limits. Needs to be a subclass of *RewardFunction*.

        Visualization:
            Visualization of the motors states. Needs to be a subclass of *ElectricMotorVisualization*
    
    Attributes:

        State Variables:
            Each environment has got a list of state variables that are defined by the physical system.
            These define the names and order for all further state arrays in the modules. These states are announced to the
            other modules by announcing the physical system to them, which contains the property ``state_names``.
            **Example:**  ``['omega', 'torque','i', 'u', 'u_sup']``

        Limits:
            Returns a list of limits of all states in the observation.
        
        Nominal Values:
            Returns a list of nominal values of all states in the observation.

    Observation:
        Type: Tuple(State_Space, Reference_Space)
            The observation is always a tuple of the State Space of the Physical System and the Reference Space of the
            Reference Generator. In all current Physical Systems and Reference Generators these Spaces are normalized,
            continuous, multidimensional boxes in [-1, 1] or [0, 1].

    Actions:
        Type: Discrete() / Box() / MultiDiscrete()
            The action space of the environments are the action spaces of the physical systems. In all current physical
            systems the action spaces are specified by its PowerElectronicConverter and either a continuous,
            multidimensional box or discrete.

    Reward:
        The reward and the reward range are specified by the RewardFunction. In general the reward is higher the closer
        the motor state follows the reference trajectories.

    Episode Termination:
        Episode terminations can be initiated by the reference generator, or the reward function.
        A reference generator might terminate an episode, if the reference has ended.
        The reward function can terminate an episode, if a physical limit of the motor has been violated.
    """

    @property
    def physical_system(self):
        """PhysicalSystem: The Physical System of the Environment"""
        return self._physical_system

    @property
    def reference_generator(self):
        """ReferenceGenerator: The ReferenceGenerator of the Environment"""
        return self._reference_generator

    @reference_generator.setter
    def reference_generator(self, reference_generator):
        """Sets a new reference generator for the environment. Afterwards, a reset is required.

        Args:
            reference_generator(ReferenceGenerator): The new reference generator of the environment.
        """
        self._reference_generator = reference_generator
        self._done = True

    @property
    def reward_function(self):
        """RewardFunction: The RewardFunction of the environment"""
        return self._reward_function

    @reward_function.setter
    def reward_function(self, reward_function):
        """Sets a new reward function for the environment. Afterwards, a reset is required."""
        self._reward_function = reward_function
        self._done = True

    @property
    def constraint_monitor(self):
        """ConstraintMonitor: The ConstraintMonitor of the environment."""
        return self._constraint_monitor

    @property
    def limits(self):
        """List of limits of all states in the observation in the same order"""
        return self._physical_system.limits

    @property
    def state_names(self):
        """Returns a list of state names of all states in the observation."""
        return self._physical_system.state_names

    @property
    def reference_names(self):
        """Returns a list of names of the states in the reference in the same order"""
        return self._reference_generator.reference_names

    @property
    def nominal_state(self):
        """Returns a list of nominal values of all states in the observation in that order"""
        return self._physical_system.nominal_state

    @property
    def visualizations(self):
        """Returns a list of all active motor visualizations."""
        return self._visualizations

    def __init__(self, physical_system, reference_generator, reward_function, visualizations=(),
                 callbacks=(), constraints=(), state_action_processors=()):
        """
        Args:
            physical_system(PhysicalSystem): The physical system of this environment.
            reference_generator(ReferenceGenerator): The reference generator of this environment.
            reward_function(RewardFunction): The reward function of this environment.
            visualizations(Iterable[ElectricMotorVisualization]): The visualizations of this environment.
            constraints(Iterable[Constraint/str/callable] / ConstraintMonitor): A list of constraints
             or an already initialized  ConstraintMonitor object can be passed here.
                    - Iterable[Constraint/str/Callable]: Pass a list with initialized Constraints and/or state names. Then,
                    a ConstraintMonitor object with the Constraints and additional LimitConstraints on the passed names
                    is created. Furthermore, the string 'all' inside the list will create a ConstraintMonitor that
                    observes the limit on each state.
                    - ConstraintMonitor: Pass an initialized ConstraintMonitor object that will be used directly as
                        ConstraintMonitor in the environment.
            state_filter(Iterable[str]): Selection of states that are shown in the observation.
            state_action_processors(Iterable[StateActionProcessor]): StateActionProcessor instances to be wrapped around
                the physical system.
            callbacks(Iterable[Callback]): Callbacks being called in the environment
        """
        self._physical_system = physical_system
        self._reference_generator = reference_generator
        self._reward_function = reward_function
        self._visualizations = tuple(visualizations)
        if isinstance(constraints, gem.core.ConstraintMonitor):
            cm = constraints
        else:
            limit_constraints = [constraint for constraint in constraints if type(constraint) is str]
            additional_constraints = [constraint for constraint in constraints if isinstance(constraint, gem.Constraint)]
            cm = gem.core.ConstraintMonitor(limit_constraints, additional_constraints)
        self._constraint_monitor = cm

        # Announcement of the modules among each other
        for state_action_processor in state_action_processors:
            self._physical_system = state_action_processor.set_physical_system(self._physical_system)
        self._reference_generator.set_modules(self.physical_system)
        self._constraint_monitor.set_modules(self.physical_system)
        self._reward_function.set_modules(self.physical_system, self._reference_generator, self._constraint_monitor)

        # Initialization of the state filter and the spaces
        self.observation_space = gym.spaces.Tuple((
            self.physical_system.state_observation_space,
            self._reference_generator.reference_space
        ))

        self.action_space = self.physical_system.action_space
        self.reward_range = self._reward_function.reward_range

        self._done = True

        self._callbacks = tuple(callbacks) + tuple(self._visualizations)
        self._call_callbacks('set_env', self)

    def _call_callbacks(self, func_name, *args):
        """Calls each callback's func_name function with *args"""
        for callback in self._callbacks:
            func = getattr(callback, func_name)
            func(*args)
            
    def reset(self):
        """Resets the environment and all its modules to an initial state.

        Returns:
             The initial observation consisting of the initial state and initial reference.
        """
        self._call_callbacks('on_reset_begin')
        self._done = False
        state = self._physical_system.reset()
        self.reference_generator.reset(state)
        reference = self.reference_generator.get_reference_observation(state)
        self._reward_function.reset()
        self._call_callbacks('on_reset_end', state, reference)
        return state, reference

    def render(self, mode='human'):
        """Update the visualization of the motor."""
        for visualization in self._visualizations:
            visualization.render()

    def step(self, action):
        """Performs one simulation step of the environment with an action of the action space.

        Args:
            action: Action to play on the environment.

        Returns:
            observation(Tuple(ndarray(float),ndarray(float)): Tuple of the new state and the next reference.
            reward(float): Amount of reward received for the last step.
            done(bool): Flag, indicating if a reset is required before new steps can be taken.
            {}: An empty dictionary for consistency with the OpenAi Gym interface.
        """

        assert not self._done, 'A reset is required before the environment can perform further steps'
        self._call_callbacks('on_step_begin', self.physical_system.k, action)
        state = self._physical_system.simulate(action)
        reference = self.reference_generator.get_reference(state)
        violation_degree = self._constraint_monitor.check_constraints(state)
        reward = self._reward_function.reward(
            state, reference, self._physical_system.k, action, violation_degree
        )
        self._done = violation_degree >= 1.0
        ref_next = self.reference_generator.get_reference_observation(state)
        self._call_callbacks(
            'on_step_end', self.physical_system.k, state, reference, reward, self._done
        )
        return (state, ref_next), reward, self._done, {}

    def seed(self, seed=None):
        sg = np.random.SeedSequence(seed)
        components = [
            self._physical_system,
            self._reference_generator,
            self._reward_function,
            self._constraint_monitor
        ] + list(self._callbacks)
        sub_sg = sg.spawn(len(components))
        for sub, rc in zip(sub_sg, components):
            if isinstance(rc, gem.RandomComponent):
                rc.seed(sub)
        return [sg.entropy]

    def close(self):
        """Closes all of the environments components.
        
        Called when the environment is deleted.
        """
        self._call_callbacks('on_close')
        self._reward_function.close()
        self._physical_system.close()
        self._reference_generator.close()