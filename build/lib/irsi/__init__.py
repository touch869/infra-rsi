"""Infra-RSI: a closed-loop experiment harness for training-infra optimization.

The package is layered so that every replaceable part is a plugin:

* ``irsi.registry``       named factories for backends, gates and surfaces
* ``irsi.contract``       the frozen task contract and surface plugins
* ``irsi.execution``      trial execution and log -> metrics extraction
* ``irsi.gates``          pass/fail checks on one trial
* ``irsi.knowledge``      skills, providers, runtime records and ledger
* ``irsi.engine``         the state machine and decision rules
"""

__version__ = "0.1.0"
