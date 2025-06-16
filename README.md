# Aurora Alerts

This Python script monitors the NOAA 3-day geomagnetic forecast and sends an email alert if the Kp-index is predicted to reach or exceed a user-defined threshold. It automatically determines the local timezone based on provided coordinates to display alert times correctly for the user.

## Features

*   Fetches the latest 3-day Kp-index forecast from NOAA SWPC.
*   Parses the text-based forecast to extract Kp values for specific time periods.
*   Converts UTC forecast times to the local timezone of the specified coordinates.
*   Sends email alerts when the Kp-index meets or exceeds a configurable threshold.
*   Uses a `.env` file for secure configuration of credentials and settings.

## Prerequisites

*   Python 3.9+ (due to the use of `zoneinfo`)
*   `pip` for installing Python packages

## Setup

1.  **Clone the repository (or download the script):**
    ```bash
    git clone https://github.com/brayvid/aurora-alert.git
    cd aurora-alert
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    Create a `requirements.txt` file with the following content:
    ```txt
    requests
    python-dotenv
    timezonefinder
    ```
    Then run:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a file named `.env` in the same directory as the script (`aurora_alerter.py`). Populate it with your settings. See the example below.

    **Example `.env` file:**
    ```env
    # --- Location Settings ---
    MAGNETIC_LATITUDE="64.8378"       # Your approximate magnetic latitude
    MAGNETIC_LONGITUDE="-147.7164"    # Your approximate magnetic longitude

    # --- Alert Settings ---
    KP_THRESHOLD="5"                  # Kp-index value to trigger an alert (e.g., 4, 5, 6)

    # --- Email Settings ---
    EMAIL_SENDER="your_email@example.com"
    EMAIL_PASSWORD="your_email_password_or_app_password" # For Gmail, use an App Password
    EMAIL_RECIPIENT="recipient1@example.com,recipient2@example.com" # Comma-separated if multiple

    # --- SMTP Server Settings (Example for Gmail) ---
    SMTP_SERVER="smtp.gmail.com"
    SMTP_PORT="587"
    ```

    **Important Notes for `.env`:**
    *   Replace placeholder values with your actual information.
    *   For `EMAIL_PASSWORD` with services like Gmail or Outlook that use 2FA, you'll likely need to generate an "App Password" specific for this script.
    *   `EMAIL_RECIPIENT` can be a single email or multiple emails separated by commas.

## Usage

Once configured, run the script from your terminal:

```bash
python aurora.py