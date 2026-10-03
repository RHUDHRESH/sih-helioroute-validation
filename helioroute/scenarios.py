"""All traces are manufactured. No weather data or measured hardware is implied."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
from .model import Parameters, Step


def load_scenarios(path):
    config = json.loads(Path(path).read_text())
    if config.get('schema_version') != 1:
        raise ValueError('Unsupported experiment schema_version; expected 1')
    result = []
    for spec in config['scenarios']:
        parameters = Parameters(**(config['default_parameters'] | spec.get('parameters', {})))
        parameters.validate()
        if not math.isfinite(spec['dt_s']) or spec['dt_s'] <= 0:
            raise ValueError('dt_s must be positive and finite')
        if 'generator' in spec:
            if spec['generator'] != 'asymmetric_day':
                raise ValueError('Unknown synthetic generator')
            rng = random.Random(config['seed'])
            steps = []
            for n in range(spec['count']):
                hour = n*spec['dt_s']/3600
                sun = max(0., math.sin(math.pi*(hour-6)/12)) if 6 <= hour <= 18 else 0.
                cloud = 0.8 + 0.2*rng.random()
                steps.append(Step(pv_a_w=380*sun*cloud, pv_b_w=65*sun,
                                  load_a_w=45+8*rng.random(),
                                  load_b_w=155+30*(8 <= hour < 18)+15*rng.random()))
        else:
            steps = [Step(**item) for item in spec['steps']]
        for step in steps:
            step.validate()
        result.append((spec, parameters, steps))
    if len({s[0]['id'] for s in result}) != len(result):
        raise ValueError('Duplicate scenario ID')
    return config, result
