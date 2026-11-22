# ImgGrab
Paste a website link, get all its images as a ZIP. Mobile-friendly.

## Run on a computer
    pip install -r requirements.txt
    python app.py        # open http://localhost:5000

## Put it online (free tiers: Render, Railway, Fly.io)
1. Upload this folder to a GitHub repository.
2. On Render: New > Web Service > connect the repo.
   Build command: pip install -r requirements.txt
   Start command: gunicorn app:app --timeout 150 --workers 1 --threads 4
3. Open the URL it gives you, from your phone.

## Sites that load photos with JavaScript
Add `playwright` to requirements.txt and run `playwright install chromium` in the build step,
then choose "Yes" on the JavaScript option. (Not available on every free host.)

## Notes
- Private/internal addresses are blocked so the tool can't be used to probe networks.
- Jobs are deleted after 1 hour. Each job stops after 90 seconds (set TIME_BUDGET to change).
- Use only on websites you own or have permission to copy from.
