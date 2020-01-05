"""Provides the `MonopileDesign` class."""

__author__ = "Jake Nunemaker"
__copyright__ = "Copyright 2019, National Renewable Energy Laboratory"
__maintainer__ = "Jake Nunemaker"
__email__ = "jake.nunemaker@nrel.gov"


from math import pi, log

from scipy.optimize import fsolve

from ORBIT.phases.design import DesignPhase


class MonopileDesign(DesignPhase):
    """Monopile Design Class."""

    expected_config = {
        "site": {"depth": "float", "mean_windspeed": "float"},
        "plant": {"num_turbines": "int"},
        "turbine": {
            "rotor_diameter": "float",
            "hub_height": "float",
            "rated_windspeed": "float",
        },
        "monopile_design": {
            "yield_stress": "float (optional)",
            "load_factor": "float (optional)",
            "material_factor": "float (optional)",
            "monopile_density": "float (optional)",
            "monopile_modulus": "float (optional)",
            "monopile_tp_connection_thickness": "float (optional)",
            "transition_piece_density": "float (optional)",
            "transition_piece_thickness": "float (optional)",
            "transition_piece_length": "float (optional)",
            "soil_coefficient": "float (optional)",
            "air_density": "float (optional)",
            "weibull_scale_factor": "float (optional)",
            "weibull_shape_factor": "float (optional)",
            "turb_length_scale": "float (optional)",
            "design_time": "float (optional)",
            "design_cost": "float (optional)",
            "monopile_steel_cost": "float (optional)",
            "tp_steel_cost": "float (optional)",
        },
    }

    output_config = {
        "monopile": {
            "type": "Monopile",
            "diameter": "float",
            "thickness": "float",
            "moment": "float",
            "embedment_length": "float",
            "length": "float",
            "weight": "float",
            "deck_space": "float",
        },
        "transition_piece": {
            "type": "Transition Piece",
            "length": "float",
            "weight": "float",
            "deck_space": "float",
        },
    }

    def __init__(self, config, **kwargs):
        """
        Creates an instance of MonopileDesign.

        Parameters
        ----------
        config : dict
        """

        config = self.initialize_library(config, **kwargs)
        self.config = self.validate_config(config)
        self.extract_defaults()
        self._outputs = {}

    def run(self):
        """
        Main run function. Passes required config parameters to
        :py:meth:`.design_monopile`.
        """

        _kwargs = self.config.get("monopile_design", {})
        self._outputs["monopile"] = self.design_monopile(
            mean_windspeed=self.config["site"]["mean_windspeed"],
            site_depth=self.config["site"]["depth"],
            rotor_diameter=self.config["turbine"]["rotor_diameter"],
            hub_height=self.config["turbine"]["hub_height"],
            rated_windspeed=self.config["turbine"]["rated_windspeed"],
            **_kwargs,
        )

        self._outputs["transition_piece"] = self.design_transition_piece(
            self.monopile_sizing["diameter"],
            self.monopile_sizing["thickness"],
            **_kwargs,
        )

    def design_monopile(
        self,
        mean_windspeed,
        site_depth,
        rotor_diameter,
        hub_height,
        rated_windspeed,
        **kwargs,
    ):
        """
        Solves system of equations for the required pile diameter to satisfy
        the 50 year extreme operating gust moment. Using the result from the
        diameter equation, calculates the wall thickness and the required
        embedment length and other important sizing parameters.

        Parameters
        ----------
        mean_windspeed : int | float
            Mean wind speed at site (m/s).
        site_depth : int | float
            Water depth at site (m).
        rotor_diameter : int | float
            Rotor diameter (m).
        hub_height : int | float
            Hub height above mean sea level (m).
        rated_windspeed : int | float
            Rated windspeed of turbine (m/s).

        Returns
        -------
        sizing : dict
            Dictionary of monopile sizing.

            - ``diameter`` - Pile diameter (m)
            - ``thickness`` - Pile wall thickness (m)
            - ``moment`` - Pile bending moment of inertia (m4)
            - ``embedment_length`` - Pile embedment length (m)
            - ``length`` - Total pile length (m)
            - ``weight`` - Pile weight (t)
            - ``type`` - `'Monopile'`

        References
        ----------
        This class was adapted from [#arany2017]_.

        .. [#arany2017] Laszlo Arany, S. Bhattacharya, John Macdonald,
           S.J. Hogan, Design of monopiles for offshore wind turbines in 10
           steps, Soil Dynamics and Earthquake Engineering,
           Volume 92, 2017, Pages 126-152, ISSN 0267-7261,
        """

        yield_stress = kwargs.get("yield_stress", 355000000)  # PA
        material_factor = kwargs.get("material_factor", 1.1)
        M_50y = self.calculate_50year_wind_moment(
            mean_windspeed=mean_windspeed,
            site_depth=site_depth,
            rotor_diameter=rotor_diameter,
            hub_height=hub_height,
            rated_windspeed=rated_windspeed,
            **kwargs,
        )

        data = (yield_stress, material_factor, M_50y)
        sizing = {}

        # Monopile sizing
        sizing["diameter"] = fsolve(self.pile_diam_equation, 10, args=data)[0]
        sizing["thickness"] = self.pile_thickness(sizing["diameter"])
        sizing["moment"] = self.pile_moment(
            sizing["diameter"], sizing["thickness"]
        )
        sizing["embedment_length"] = self.pile_embedment_length(
            sizing["moment"], **kwargs
        )

        # Total length
        airgap = kwargs.get("airgap", 10)  # m
        sizing["length"] = sizing["embedment_length"] + site_depth + airgap
        sizing["weight"] = self.pile_mass(
            Dp=sizing["diameter"],
            tp=sizing["thickness"],
            Lt=sizing["length"],
            **kwargs,
        )

        # Deck space
        sizing["deck_space"] = sizing["diameter"] ** 2

        # Required for simulation
        sizing["type"] = "Monopile"

        self.monopile_sizing = sizing

        return sizing

    @staticmethod
    def design_transition_piece(D_p, t_p, **kwargs):
        """
        Designs transition piece given the results of the monopile design.

        Based on Arany 2016, sections 2.2.7 - 2.2.8.

        Parameters
        ----------
        monopile_diameter : int | float
            Diameter of the designed monopile.

        Returns
        -------
        tp_design : dict
            Transition piece design parameters.
        """

        # Defaults to a bolted connection
        t_c = kwargs.get("monopile_tp_connection_thickness", 0.0)

        dens_tp = kwargs.get("transition_piece_density", 7860)  # kg/m3
        t_tp = kwargs.get("transition_piece_thickness", t_p)
        L_tp = kwargs.get("transition_piece_length", 25)
        D_tp = D_p + 2 * (t_c + t_tp)  # Arany 2016, Section 2.2.7

        # Arany 2016, Section 2.2.8
        m_tp = (
            dens_tp * (D_p + 2 * t_c + t_tp) * pi * t_tp * L_tp
        ) / 907.185  # t

        tp_design = {
            "type": "Transition Piece",
            "thickness": t_tp,
            "diameter": D_tp,
            "weight": m_tp,
            "length": L_tp,
            "deck_space": D_tp ** 2,
        }

        return tp_design

    @property
    def design_result(self):
        """
        Returns the results of :py:meth:`.design_monopile`.
        """

        if not self._outputs:
            raise Exception("Has MonopileDesign been ran yet?")

        return self._outputs

    @property
    def total_phase_cost(self):
        """Returns total phase cost in $USD."""

        _design = self.config.get("monopile_design", {})
        design_cost = _design.get("design_cost", 0.0)
        material_cost = sum([v for _, v in self.material_cost.items()])

        return design_cost + material_cost

    @property
    def total_phase_time(self):
        """Returns total phase time in hours."""

        phase_time = self.config["monopile_design"].get("design_time", 0.0)
        return phase_time

    @property
    def detailed_output(self):
        """Returns detailed phase information."""

        return {}

    @property
    def material_cost(self):
        """Returns the material cost of the monopile and transition piece."""

        if not self._outputs:
            raise Exception("Has MonopileDesign been ran yet?")

        num_turbines = self.config["plant"]["num_turbines"]
        mono_weight = self._outputs["monopile"]["weight"] * num_turbines
        tp_weight = self._outputs["transition_piece"]["weight"] * num_turbines

        out = {
            "monopile": mono_weight * self.monopile_steel_cost,
            "transition_piece": tp_weight * self.tp_steel_cost,
        }

        return out

    @property
    def monopile_steel_cost(self):
        """Returns the cost of monopile steel (USD/t) fully fabricated."""

        _design = self.config.get("monopile_design", {})
        _key = "monopile_steel_cost"

        try:
            cost = _design.get(_key, self.defaults[_key])

        except KeyError:
            raise Exception("Cost of monopile steel not found.")

        return cost

    @property
    def tp_steel_cost(self):
        """
        Returns the cost of transition piece steel (USD/t) fully fabricated.
        """

        _design = self.config.get("monopile_design", {})
        _key = "tp_steel_cost"

        try:
            cost = _design.get(_key, self.defaults[_key])

        except KeyError:
            raise Exception("Cost of transition piece steel not found.")

        return cost

    @staticmethod
    def pile_mass(Dp, tp, Lt, **kwargs):
        """
        Calculates the total monopile mass in tonnes.

        Parameters
        ----------
        Dp : int | float
            Pile diameter (m).
        tp : int | float
            Pile wall thickness (m).
        Lt : int | float
            Total pile length (m).

        Returns
        -------
        mt : float
            Total pile mass (t).
        """

        density = kwargs.get("monopile_density", 7860)  # kg/m3
        volume = (pi / 4) * (Dp ** 2 - (Dp - tp) ** 2) * Lt
        mass = density * volume / 907.185

        return mass

    @staticmethod
    def pile_embedment_length(Ip, **kwargs):
        """
        Calculates required pile embedment length.
        Source: Arany & Bhattacharya (2016)
        - Equation 102

        Parameters
        ----------
        Ip : int | float
            Pile moment of inertia (m4)

        Returns
        -------
        Lp : float
            Required pile embedment length (m).
        """

        monopile_modulus = kwargs.get("monopile_modulus", 200e9)  # Pa
        soil_coefficient = kwargs.get("soil_coefficient", 4000000)  # N/m3

        Lp = 4 * ((monopile_modulus * Ip) / soil_coefficient) ** 0.2

        return Lp

    @staticmethod
    def pile_thickness(Dp):
        """
        Calculates pile wall thickness.
        Source: Arany & Bhattacharya (2016)
        - Equation 1

        Parameters
        ----------
        Dp : int | float
            Pile diameter (m).

        Returns
        -------
        tp : float
            Pile Wall Thickness (m)
        """

        tp = 0.00635 + Dp / 100

        return tp

    @staticmethod
    def pile_moment(Dp, tp):
        """
        Equation to calculate the pile bending moment of inertia.

        Parameters
        ----------
        Dp : int | float
            Pile diameter (m).
        tp : int | float
            Pile wall thickness (m).

        Returns
        -------
        Ip : float
            Pile bending moment of inertia
        """

        Ip = 0.125 * ((Dp - tp) ** 3) * tp * pi

        return Ip

    @staticmethod
    def pile_diam_equation(Dp, *data):
        """
        Equation to be solved for Pile Diameter. Combination of equations 99 &
        101 in this paper:
        Source: Arany & Bhattacharya (2016)
        - Equations 99 & 101

        Parameters
        ----------
        Dp : int | float
            Pile diameter (m).

        Returns
        -------
        res : float
            Reduced equation result.
        """

        yield_stress, material_factor, M_50y = data
        A = (yield_stress * pi) / (4 * material_factor * M_50y)
        res = A * ((0.99 * Dp - 0.00635) ** 3) * (0.00635 + 0.01 * Dp) - Dp

        return res

    def calculate_50year_wind_moment(
        self,
        mean_windspeed,
        site_depth,
        rotor_diameter,
        hub_height,
        rated_windspeed,
        **kwargs,
    ):
        """
        Calculates the 50 year extreme wind moment using methodology from
        DNV-GL. Source: Arany & Bhattacharya (2016)
        - Equation 30

        Parameters
        ----------
        mean_windspeed : int | float
            Mean wind speed at site (m/s).
        site_depth : int | float
            Water depth at site (m).
        rotor_diameter : int | float
            Rotor diameter (m).
        hub_height : int | float
            Hub height above mean sea level (m).
        rated_windspeed : int | float
            Rated windspeed of turbine (m/s).
        load_factor : float
            Added safety factor on the extreme wind moment.
            Default: 1.35

        Returns
        -------
        M_50y : float
            50 year extreme wind moment (N-m).
        """

        load_factor = kwargs.get("load_factor", 1.35)

        F_50y = self.calculate_50year_wind_load(
            mean_windspeed=mean_windspeed,
            rotor_diameter=rotor_diameter,
            rated_windspeed=rated_windspeed,
            **kwargs,
        )

        M_50y = F_50y * (site_depth + hub_height)

        return M_50y * load_factor

    def calculate_50year_wind_load(
        self, mean_windspeed, rotor_diameter, rated_windspeed, **kwargs
    ):
        """
        Calculates the 50 year extreme wind load using methodology from DNV-GL.
        Source: Arany & Bhattacharya (2016)
        - Equation 29

        Parameters
        ----------
        mean_windspeed : int | float
            Mean wind speed at site (m/s).
        rotor_diam : int | float
            Rotor diameter (m).
        rated_windspeed : int | float
            Rated windspeed of turbine (m/s).

        Returns
        -------
        F_50y : float
            50 year extreme wind load (N).
        """

        dens = kwargs.get("air_density", 1.225)
        swept_area = pi * (rotor_diameter / 2) ** 2

        ct = self.calculate_thrust_coefficient(rated_windspeed=rated_windspeed)

        U_eog = self.calculate_50year_extreme_gust(
            mean_windspeed=mean_windspeed,
            rated_windspeed=rated_windspeed,
            rotor_diameter=rotor_diameter,
            **kwargs,
        )

        F_50y = 0.5 * dens * swept_area * ct * (rated_windspeed + U_eog) ** 2

        return F_50y

    @staticmethod
    def calculate_thrust_coefficient(rated_windspeed):
        """
        Calculates the thrust coefficient using rated windspeed.
        Source: Frohboese & Schmuck (2010)

        Parameters
        ----------
        rated_windspeed : int | float
            Rated windspeed of turbine (m/s).

        Returns
        -------
        ct : float
            Coefficient of thrust.
        """

        ct = min(
            [3.5 * (2 * rated_windspeed + 3.5) / (rated_windspeed ** 2), 1]
        )

        return ct

    @staticmethod
    def calculate_50year_extreme_ws(mean_windspeed, **kwargs):
        """
        Calculates the 50 year extreme wind speed using methodology from DNV-GL.
        Source: Arany & Bhattacharya (2016)
        - Equation 27

        Parameters
        ----------
        mean_windspeed : int | float
            Mean wind speed (m/s).
        shape_factor : int | float
            Shape factor of the Weibull distribution.

        Returns
        -------
        U_50y : float
            50 year extreme wind speed (m/s).
        """

        scale_factor = kwargs.get("weibull_scale_factor", mean_windspeed)
        shape_factor = kwargs.get("weibull_shape_factor", 2)
        U_50y = scale_factor * (-log(1 - 0.98 ** (1 / 52596))) ** (
            1 / shape_factor
        )

        return U_50y

    def calculate_50year_extreme_gust(
        self, mean_windspeed, rotor_diameter, rated_windspeed, **kwargs
    ):
        """
        Calculates the 50 year extreme wind gust using methodology from DNV-GL.
        Source: Arany & Bhattacharya (2016)
        - Equation 28

        Parameters
        ----------
        mean_windspeed : int | float
            Mean wind speed at site (m/s).
        rotor_diameter : int | float
            Rotor diameter (m).
        rated_windspeed : int | float
            Rated windspeed of turbine (m/s).
        turb_length_scale : int | float
            Turbulence integral length scale (m).

        Returns
        -------
        U_eog : float
            Extreme operating gust speed (m/s).
        """

        length_scale = kwargs.get("turb_length_scale", 340.2)

        U_50y = self.calculate_50year_extreme_ws(mean_windspeed, **kwargs)
        U_1y = 0.8 * U_50y

        U_eog = min(
            [
                (1.35 * (U_1y - rated_windspeed)),
                (3.3 * 0.11 * U_1y)
                / (1 + (0.1 * rotor_diameter) / (length_scale / 8)),
            ]
        )

        return U_eog
