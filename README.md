# HiringFunnel

**Stop copy-pasting the same answers into 50 LinkedIn Easy Apply forms.**

HiringFunnel runs a real browser, fills out applications with your info, and submits them while you do literally anything else.

![Demo](demo.gif)

## Quick Start

```bash
git clone https://github.com/pypesdev/hiring-funnel && cd hiring-funnel
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python hiringfunnel.py
```

## How It Works

1. Add your LinkedIn credentials and basic info (phone, location, experience)
2. Set target job titles and locations
3. Select **Start** — watch it apply to jobs in a real browser window

## Development

### Prerequisites

- **Python 3.10+**

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
python hiringfunnel.py
```

### Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

## License

MIT
