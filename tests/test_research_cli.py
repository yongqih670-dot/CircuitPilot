from circuitpilot.experiments.run import _default_config, build_parser


def test_research_cli_builds_the_same_common_config_as_yaml_path() -> None:
    arguments = build_parser().parse_args(
        [
            "--circuit",
            "rc_lowpass",
            "--method",
            "random",
            "--seed",
            "5",
            "--budget",
            "7",
            "--output-dir",
            "research_runs",
        ]
    )

    config = _default_config(arguments)

    assert config.circuit_name == "rc_lowpass"
    assert config.method == "random"
    assert config.seed == 5
    assert config.simulation_budget == 7
    assert set(config.search_space_by_name) == {"resistance", "capacitance"}
    assert config.objectives[0].metric == "bandwidth"
