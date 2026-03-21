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
python3 hiringfunnel.py
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
.venv/bin/python -m pytest tests/ -v  
```
## Docker

Run FoxyApply in a container with headless Chrome — no local browser or Python setup needed.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed and running

### Setup

**1. Copy the example env file and fill in your credentials:**
```bash
cp .env.example .env
```

Edit `.env`:
```env
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=yourpassword
```

**2. Create a profile** (first run, interactive):
```bash
docker build -t foxyapply .
docker run -it --env-file .env foxyapply python hiringfunnel.py
```

This launches the TUI so you can create and save a profile. Profiles are stored in `profiles.json`.

**3. Run non-interactively** (after a profile is created):
```bash
docker run --env-file .env \
  -v $(pwd)/profiles.json:/app/profiles.json \
  -v $(pwd)/logs:/app/logs \
  foxyapply python hiringfunnel.py --run "your-profile-name" --headless
```

The `-v` flags persist your profiles and logs outside the container.

### Docker Compose (recommended)
```bash
cp .env.example .env
# Fill in your credentials in .env

docker compose up --build
```

To change which profile runs, edit `docker-compose.yml`:
```yaml
command: ["python", "hiringfunnel.py", "--run", "your-profile-name", "--headless"]
```

### Notes

- Chrome runs in headless mode inside Docker — you won't see a browser window
- Logs are written to `./logs/hiringfunnel.log`
- If LinkedIn requires manual login verification, run interactively with `-it` and remove `--headless`



## License

MIT
