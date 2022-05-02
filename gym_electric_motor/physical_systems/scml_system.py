import numpy as np
from typing import TYPE_CHECKING
import warnings

import gym_electric_motor as gem
from ..core.random_component import RandomComponent
from ..core import PhysicalSystem

if TYPE_CHECKING:
    from gym_electric_motor.physical_systems import PowerElectronicConverter, \
        ElectricMotor, MechanicalLoad, OdeSolver, VoltageSupply


class SCMLSystem(PhysicalSystem, RandomComponent):
    """The SCML(Supply-Converter-Motor-Load)-System is used for the simulation of a drive system.
    
    This system consists of these components (SCML) and a solver for the electrical ODE of the motor and mechanical load.
    """

    @property
    def tau(self) -> float:
        return self._tau

    @property
    def state_names(self):
        return [name for comp in self._scml_components for name in comp.observation_names]

    @property
    def action_space(self):
        return self._converter.action_space

    @property
    def state_observation_space(self):
        return self._observation_space

    @property
    def initial_ode_value(self):
        return self._initial_ode_value

    @initial_ode_value.setter
    def initial_ode_value(self, value):
        self._initial_ode_value[:] = value

    @property
    def state_units(self):
        return [unit for comp in self._scml_components for unit in comp.observation_units]

    @property
    def state_tex_names(self):
        return [tex_name for comp in self._scml_components for tex_name in comp.observation_tex_names]
    
    @property
    def state_tex_units(self):
        return [tex_unit for comp in self._scml_components for tex_unit in comp.observation_tex_units]

    @property
    def limits(self):
        if self._limits is None:
            self._limits = np.array([limit for comp in self._scml_components for limit in comp.limits])
        return self._limits

    @property
    def nominal_state(self):
        if self._nominal_state is None:
            self._nominal_state = np.array([nom_state for comp in self._scml_components for nom_state in comp.nominal_state])
        return self._nominal_state
    
    @property
    def supply(self):
        """The voltage supply instance in the physical system"""
        return self._supply

    @property
    def converter(self):
        """The power electronic converter instance in the system"""
        return self._converter

    @property
    def electric_motor(self):
        """The electrical motor instance of the system"""
        return self._electric_motor

    @property
    def mechanical_load(self):
        """The mechanical load instance in the system"""
        return self._mechanical_load

    def __init__(
        self,
        converter: 'PowerElectronicConverter',
        motor: 'ElectricMotor',
        load: 'MechanicalLoad',
        supply: 'VoltageSupply',
        ode_solver: 'OdeSolver',
        tau: float = 1e-4,
        calc_jacobian: bool = None
    ):
        """
        Args:
            converter(PowerElectronicConverter): Converter for the system
            motor(ElectricMotor): Motor of the system
            load(MechanicalLoad): Mechanical Load of the System
            supply(VoltageSupply): Voltage Supply
            ode_solver(OdeSolver): Ode Solver to use in this setting
            tau(float): discrete time step of the system
            calc_jacobian(bool): If True, the jacobian matrices will be taken into account for the ode-solvers.
                Default: The jacobians are used, if available
        """
        PhysicalSystem.__init__(self)
        RandomComponent.__init__(self)

        self._converter = converter
        self._electric_motor = motor
        self._mechanical_load = load
        self._supply = supply
        self._ode_solver = ode_solver
        self._scml_components = load, motor, converter, supply
        self._tau = float(tau)
        assert self._supply.supply_shape == self._converter.supply_shape
        assert self._converter.output_shape == self._electric_motor.input_shape
        assert self._electric_motor.torque_shape == self._mechanical_load.speed_shape

        self._random_components = (
            self._supply, self._converter, self._electric_motor, self._mechanical_load, self._ode_solver
        )

        self._motor_state = None
        self._load_state = None

        if calc_jacobian is None:
            calc_jacobian = self._electric_motor.HAS_JACOBIAN and self._mechanical_load.HAS_JACOBIAN
        
        if calc_jacobian and self._electric_motor.HAS_JACOBIAN and self._mechanical_load.HAS_JACOBIAN:
            jac = self._system_jacobian
        else:
            jac = None
        
        if calc_jacobian and jac is None:
            warnings.warn('Jacobian Matrix is not provided for either the motor or the load Model')

        self._ode_solver.set_system_equation(self._system_equation, jac)

        self._mechanical_load.set_j_rotor(self._electric_motor.motor_parameter['j_rotor'])

        self._t = 0
        c = [component.observation_space for component in self._scml_components]
        system_observation_space = gem.utils.concatenate_boxes(*c)
        self._observation_space = system_observation_space
        self._state_names = [observation for component in self._scml_components for observation in component.observation_names]        
        
        self._load_ode_slice = slice(0, load.ode_size)
        self._motor_ode_slice = slice(load.ode_size, load.ode_size + motor.ode_size)

        self._limits = None
        self._nominal_state = None
        self._initial_ode_value = np.zeros(self.electric_motor.ode_size + self.mechanical_load.ode_size, dtype=float)
        self.system_observation = np.zeros_like(self._state_names, dtype=float)
        self._system_derivative = np.zeros(load.ode_size + motor.ode_size)
        self._system_jacobian = np.zeros((load.ode_size + motor.ode_size, load.ode_size + motor.ode_size))

    def seed(self, seed=None):
        RandomComponent.seed(self, seed)
        sub_seeds = self.seed_sequence.spawn(len(self._random_components))
        for component, sub_seed in zip(self._random_components, sub_seeds):
            if isinstance(component, gem.RandomComponent):
                component.seed(sub_seed)

    def simulate(self, action):
        # Docstring of superclass        
        switching_times = self._converter.set_action(action, self._t) + [self._t + self._tau]

        for t in switching_times:
            i_in = self._electric_motor.i_in(t, self._motor_state)
            i_sup = self._converter.i_sup(i_in)
            u_sup = self._supply.get_u_sup(self._t, i_sup)
            u_in = self._converter.convert(self._ode_solver.t, i_in, u_sup)
            self._electric_motor.set_u_in(u_in)
            ode_state = self._ode_solver.integrate(t)
        
        self._count_step()
        self._motor_state = ode_state[self._motor_state_slice]
        self._load_state = ode_state[self._load_state_slice]


        self.system_observation = np.concatenate((
                self._mechanical_load.get_observation(self._load_state),
                self._electric_motor.get_observation(self._motor_state),
                self._converter.get_observation(),
                self._supply.get_observation()
        ))
        return self.system_observation / self._limits

    def _system_equation(self, t, state):
        """Systems differential equation system.

        It is a concatenation of the motors electrical ode system and the mechanical ode system.

        Args:
            t(float): Current system time
            state(ndarray(float)): Current systems ODE-State

        Returns:
            ndarray(float): The derivatives of the ODE-State. Based on this, the Ode Solver calculates the next state.
        """
        motor_state = state[self._motor_ode_slice]
        load_state = state[self._load_ode_slice]
        omega = self._mechanical_load.get_omega(load_state)
        self._system_derivative[self._motor_ode_slice] = self._electric_motor.electrical_ode(motor_state, omega)
        torque = self._electric_motor.torque(motor_state)
        self._system_derivative[self._load_ode_slice] = self._mechanical_load.mechanical_ode(t, load_state, torque)
        return self._system_derivative

    def _system_jacobian(self, t, state):
        motor_state = state[self._motor_ode_slice]
        load_state = state[self._load_ode_slice]
        omega = self._mechanical_load.get_omega(load_state)
        motor_jac, el_state_over_omega, torque_over_el_state = \
            self._electric_motor.electrical_jacobian(motor_state, omega)
        torque = self._electric_motor.torque(motor_state)
        load_jac, load_over_torque = self._mechanical_load.mechanical_jacobian(
            t, state[self._load_ode_idx], torque
        )
        
        system_jac[:load_jac.shape[0], :load_jac.shape[1]] = load_jac
        system_jac[-motor_jac.shape[0]:, -motor_jac.shape[1]:] = motor_jac
        system_jac[-motor_jac.shape[0]:, [self._omega_ode_idx]] = el_state_over_omega.reshape((-1, 1))
        system_jac[:load_jac.shape[0], load_jac.shape[1]:] = np.matmul(
            load_over_torque.reshape(-1, 1), torque_over_el_state.reshape(1, -1)
        )
        return system_jac

    def reset(self):
        """Resets all the systems components to an initial state.

        Returns:
             numpy.ndarray[float]: The new state of the system.
        """
        PhysicalSystem.reset(self)
        self.next_generator()
        self._mechanical_load.reset()
        self._electric_motor.reset()
        self._converter.reset()
        self._supply.reset()

        self._ode_solver.set_initial_value(self.initial_ode_value, self._t)
        self._motor_state = self._ode_solver.y[self._motor_ode_slice]
        self._load_state = self._ode_solver.y[self._load_ode_slice]
        self.system_observation = np.concatenate((
            self._mechanical_load.get_observation(self._load_state),
            self._electric_motor.get_observation(self._motor_state),
            self._converter.get_observation(),
            self._supply.get_observation()
        ))
        return self.system_observation / self._limits