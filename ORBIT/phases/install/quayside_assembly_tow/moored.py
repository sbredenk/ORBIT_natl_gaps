"""Installation strategies for moored floating systems."""

__author__ = "Jake Nunemaker"
__copyright__ = "Copyright 2020, National Renewable Energy Laboratory"
__maintainer__ = "Jake Nunemaker"
__email__ = "jake.nunemaker@nrel.gov"


from ORBIT.core import WetStorage
from ORBIT.phases.install import InstallPhase

from .common import TurbineAssemblyLine, SubstructureAssemblyLine


class MooredSubInstallation(InstallPhase):
    """
    Installation module to model the quayside assembly, tow-out and
    installation at sea of moored substructures.
    """

    phase = "Moored Substructure Installation"

    #:
    expected_config = {
        "tow_vessel_group": "dict | str",
        "substructure": {"takt_time": "int | float"},
        "site": {"depth": "m", "distance": "km"},
        "plant": {"num_turbines": "int"},
        "turbine": "dict",
        "port": {
            "sub_assembly_lines": "int",
            "sub_storage": "int (optional, default: 2)",
            "turbine_assembly_cranes": "int",
            "assembly_storage": "int (optional, default: 2)",
            "monthly_rate": "USD/mo (optional)",
            "name": "str (optional)",
        },
    }

    def __init__(self, config, weather=None, **kwargs):
        """
        Creates an instance of MooredSubInstallation.

        Parameters
        ----------
        config : dict
            Simulation specific configuration.
        weather : np.array
            Weather data at site.
        """

        super().__init__(weather, **kwargs)

        config = self.initialize_library(config, **kwargs)
        self.config = self.validate_config(config)
        self.extract_defaults()

        self.setup_simulation(**kwargs)

    def setup_simulation(self, **kwargs):
        """
        Sets up simulation infrastructure.
        - Initializes substructure production
        - Initializes turbine assembly processes
        - Initializes towing groups
        """

        self.initialize_substructure_production()
        self.initialize_turbine_assembly()

    def initialize_substructure_production(self):
        """
        Initializes the production of substructures at port. The number of
        independent assembly lines and production time associated with a
        substructure can be configured with the following parameters:

        - self.config["substructure"]["takt_time"]
        - self.config["port"]["sub_assembly_lines"]
        """

        storage = self.config["port"].get("sub_storage", 2)
        self.wet_storage = WetStorage(self.env, storage)

        time = self.config["substructure"]["takt_time"]
        lines = self.config["port"]["sub_assembly_lines"]
        num = self.config["plant"]["num_turbines"]

        to_assemble = [1] * num

        for i in range(lines):
            a = SubstructureAssemblyLine(
                to_assemble, time, self.wet_storage, i + 1
            )

            self.env.register(a)
            a.start()

    def initialize_turbine_assembly(self):
        """
        Initializes turbine assembly lines. The number of independent lines
        can be configured with the following parameters:

        - self.config["port"]["turb_assembly_lines"]
        """

        storage = self.config["port"].get("assembly_storage", 2)
        self.assembly_storage = WetStorage(self.env, storage)

        lines = self.config["port"]["turbine_assembly_cranes"]
        turbine = self.config["turbine"]
        for i in range(lines):
            a = TurbineAssemblyLine(
                self.wet_storage, self.assembly_storage, turbine, i + 1
            )

            self.env.register(a)
            a.start()

    def initialize_towing_groups(self):
        """

        """
        pass

    @property
    def detailed_output(self):
        """"""

        # TODO:
        return {}
