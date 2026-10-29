"""Allow `python -m smslab` as an alternative to the `smslab` console script."""

import sys

from smslab.cli import main

if __name__ == "__main__":
    sys.exit(main())
