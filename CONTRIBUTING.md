# Contributing

1. Keep the project standard-library-only at runtime.
2. Never add real SMS provider clients, network transports, API-key handling, or live-recipient sending.
3. Keep safety limits enforced in code, not just in documentation.
4. Add tests for every behavior and for every new configuration field.
5. Run these checks from the repository root:

    python -m compileall -q smslab
    python -m unittest discover -s tests -v
    smslab loadtest --config examples/config.example.json --volume 5 --concurrency 2 --report /tmp/smslab-report.json

All runs must remain fully local and simulated.
