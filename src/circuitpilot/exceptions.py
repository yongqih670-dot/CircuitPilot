"""Project-specific exception types."""


class CircuitPilotError(Exception):
    """Base exception for expected CircuitPilot failures."""


class NetlistError(CircuitPilotError):
    """Raised when a netlist cannot be generated or written."""


class ConfigError(CircuitPilotError):
    """Raised when a circuit configuration file is invalid."""


class SimulationError(CircuitPilotError):
    """Raised when ngspice cannot be started or finishes unsuccessfully."""


class ParseError(CircuitPilotError):
    """Raised when an ngspice result file is missing or malformed."""


class AnalysisError(CircuitPilotError):
    """Raised when a requested measurement cannot be derived from data."""


class PlotError(CircuitPilotError):
    """Raised when a plot cannot be written."""


class SweepError(CircuitPilotError):
    """Raised when a parameter sweep or its output cannot be completed."""


class ExperimentError(CircuitPilotError):
    """Raised when experiment persistence or comparison fails."""


class OptimizationError(CircuitPilotError):
    """Raised when circuit optimization or history export fails."""


class ResearchArtifactError(CircuitPilotError):
    """Raised when a reproducibility manifest cannot be created or verified."""


class RunDirectoryError(CircuitPilotError):
    """Raised when a research run directory cannot be created or resumed safely."""


class ResearchExperimentError(CircuitPilotError):
    """Raised when a unified research experiment cannot be completed safely."""
