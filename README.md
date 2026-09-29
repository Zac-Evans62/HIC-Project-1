# PlateWise: recipe book and meal planner

## Run it
```
python -m venv venv
venv\Scripts\activate        (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

The database (`platewise.db`) is created and filled with sample recipes on first run.
To reset it, stop the app, delete `platewise.db`, and start again.

## Adding a new page
1. Create `templates/yourpage.html` starting with `{% extends 'base.html' %}`
2. In `app.py`, replace the matching `make_stub(...)` line with a real route (keep the same endpoint name).