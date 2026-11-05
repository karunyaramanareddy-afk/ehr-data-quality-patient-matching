# EHR Data Quality Demo

A small Streamlit demo for importing patient records from CSV, checking record completeness and validity, and finding possible duplicate records across source systems. The app stores imported records in a local SQLite database.

> **Demo data only:** `sample_patients.csv` contains synthetic records. Do not upload real patient or other sensitive health information to this demo.

## Requirements

- Python 3.10 or newer
- pip

## Run on Windows

Open PowerShell or Anaconda/Miniconda Prompt and run these commands from the project directory:

```powershell
cd C:\EHR
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

In Anaconda/Miniconda Prompt, activation may instead be:

```bat
conda create -n ehr-demo python=3.11 -y
conda activate ehr-demo
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit prints a local URL (usually `http://localhost:8501`) when the app is running. Stop it with **Ctrl+C** in the terminal.

## Import sample data

1. Open the **Import CSV** tab.
2. Upload `sample_patients.csv`.
3. Click **Import records**.
4. Explore the **Patient records**, **Data quality**, and **Potential matches** tabs.

The sample includes records from multiple source systems, similar records for match review, and an intentionally incomplete/invalid record for quality checks.

## CSV format

The importer accepts these columns:

```text
source_system,source_patient_id,given_name,family_name,dob,sex,phone,email,address,postal_code,national_id
```

Patient fields may be omitted or empty. If `source_system` or `source_patient_id` is omitted, the app uses the CSV filename and row number respectively. Dates should use `YYYY-MM-DD`.

The local database (`ehr_demo.db`) is created automatically and is excluded from Git.

## GitHub

After creating an empty repository on GitHub, initialize and connect this local project:

```powershell
cd C:\EHR
git init
git add .
git status
git commit -m "Initial EHR data quality demo"
git branch -M main
git remote add origin https://github.com/<YOUR-USERNAME>/<YOUR-REPOSITORY>.git
git push -u origin main
```

Replace the GitHub URL placeholder with your repository's URL. The ignore rules exclude virtual environments, local databases, and Streamlit secrets.
