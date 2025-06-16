import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import re
from datetime import datetime, time, timedelta, date # Added date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from timezonefinder import TimezoneFinder

# Load environment variables from the .env file
load_dotenv()

# --- Load Settings from Environment Variables ---
try:
    MAGNETIC_LATITUDE = float(os.getenv("MAGNETIC_LATITUDE"))
    MAGNETIC_LONGITUDE = float(os.getenv("MAGNETIC_LONGITUDE"))
    KP_THRESHOLD = int(os.getenv("KP_THRESHOLD", "5"))

    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    
    # Get the recipient string, could be one or more comma-separated emails
    RECIPIENT_STRING = os.getenv("EMAIL_RECIPIENT") 
    
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT"))

    if not all([EMAIL_SENDER, EMAIL_PASSWORD, RECIPIENT_STRING, SMTP_SERVER, SMTP_PORT]):
        raise ValueError("One or more required environment variables for email are not set (EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_SERVER, SMTP_PORT).")
    if MAGNETIC_LATITUDE is None or MAGNETIC_LONGITUDE is None:
        raise ValueError("MAGNETIC_LATITUDE and MAGNETIC_LONGITUDE must be set in the .env file.")

except (ValueError, TypeError) as e:
    print(f"Error loading settings from .env file: {e}")
    print("Please ensure your .env file is correctly formatted and all required variables are set.")
    exit()
# ---------------------------------------------

# --- Determine Local Timezone ---
LOCAL_TZ = None
LOCAL_TZ_NAME = "UTC" # Default if not found
try:
    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lng=MAGNETIC_LONGITUDE, lat=MAGNETIC_LATITUDE)
    if timezone_str:
        LOCAL_TZ = ZoneInfo(timezone_str)
        LOCAL_TZ_NAME = timezone_str
        print(f"Successfully determined local timezone: {LOCAL_TZ_NAME}")
    else:
        print(f"Warning: Could not determine timezone for lat={MAGNETIC_LATITUDE}, lon={MAGNETIC_LONGITUDE}. Defaulting to UTC.")
        LOCAL_TZ = ZoneInfo("UTC")
except ZoneInfoNotFoundError:
    print(f"Warning: Timezone '{timezone_str}' found by timezonefinder is not recognized by zoneinfo. Defaulting to UTC.")
    LOCAL_TZ = ZoneInfo("UTC")
except Exception as e:
    print(f"Error determining local timezone: {e}. Defaulting to UTC.")
    LOCAL_TZ = ZoneInfo("UTC")

UTC_TZ = ZoneInfo("UTC")
# ---------------------------------------------

def month_str_to_int(month_str):
    return datetime.strptime(month_str.strip(), "%b").month

def get_aurora_forecast():
    try:
        url = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching aurora forecast: {e}")
        return None

def parse_forecast(forecast_text, target_tz):
    high_kp_periods = []
    if not forecast_text:
        return high_kp_periods

    lines = forecast_text.splitlines()
    
    current_year = datetime.now(UTC_TZ).year 
    issued_year_found = False
    for line in lines:
        if line.startswith(":Issued:"): 
            try:
                issued_parts = line.split(":")
                if len(issued_parts) > 2:
                    issued_str = issued_parts[2].strip().split(" UTC")[0]
                    try:
                        dt_obj = datetime.strptime(issued_str, "%Y %b %d %H%M")
                    except ValueError:
                        dt_obj = datetime.strptime(issued_str, "%b %d %H%M %Y") 
                    current_year = dt_obj.year
                    issued_year_found = True
                    break
            except (ValueError, IndexError) as e:
                print(f"DEBUG: Warning: Could not parse year from issued line: '{line}'. Error: {e}. Using current system year.")
    if not issued_year_found:
         print(f"DEBUG: Warning: :Issued: line not found or unparseable for year. Using current system year: {current_year}")

    date_header_line_idx = -1
    forecast_dates_raw = []

    for i, line in enumerate(lines):
        if "NOAA Kp index breakdown" in line:
            for next_line_offset in range(1, 4): 
                current_check_idx = i + next_line_offset
                if current_check_idx < len(lines):
                    potential_date_line = lines[current_check_idx].strip()
                    if not potential_date_line: 
                        continue
                    parts = potential_date_line.split()
                    if len(parts) >= 3: 
                        try:
                            month_str_to_int(parts[0]) 
                            date_header_line_idx = current_check_idx
                            forecast_dates_raw = parts
                            break 
                        except ValueError:
                            break 
                    else:
                        break 
                else: 
                    break
            if date_header_line_idx != -1: 
                break 

    if date_header_line_idx == -1:
        print("Error: Could not find or parse the date header line in the forecast.")
        return high_kp_periods

    parsed_dates = []
    current_month_int = None
    try:
        idx = 0
        while idx < len(forecast_dates_raw) and len(parsed_dates) < 3:
            month_str = forecast_dates_raw[idx]
            current_month_int = month_str_to_int(month_str)
            idx += 1
            if idx < len(forecast_dates_raw) and forecast_dates_raw[idx].isdigit():
                day_int = int(forecast_dates_raw[idx])
                idx += 1
            else:
                raise ValueError(f"Expected day after month '{month_str}', but found '{forecast_dates_raw[idx] if idx < len(forecast_dates_raw) else 'EOF'}'")

            year_for_forecast = current_year
            if datetime.now(UTC_TZ).month == 12 and current_month_int == 1:
                year_for_forecast = current_year + 1
            parsed_dates.append(date(year_for_forecast, current_month_int, day_int))
        if len(parsed_dates) != 3:
            print(f"Error: Expected to parse 3 dates, but got {len(parsed_dates)}. Raw: {forecast_dates_raw}")
            return high_kp_periods
    except (ValueError, IndexError) as e:
        print(f"Error parsing date components from '{forecast_dates_raw}'. Error: {e}")
        return high_kp_periods

    for line_num in range(date_header_line_idx + 1, len(lines)):
        line = lines[line_num].strip()
        if not line or not re.match(r"\d{2}-\d{2}UT", line):
            continue 
        parts = line.split()
        time_period_str = parts[0] 
        kp_value_strs = parts[1:]  
        if len(kp_value_strs) < len(parsed_dates): 
            continue
        try:
            start_hour = int(time_period_str[:2])
        except ValueError:
            continue
        for i, kp_str in enumerate(kp_value_strs):
            if i >= len(parsed_dates): 
                break
            try:
                kp_index = int(float(kp_str)) 
                if kp_index >= KP_THRESHOLD:
                    forecast_date_obj = parsed_dates[i]
                    utc_start_dt = datetime.combine(forecast_date_obj, time(hour=start_hour), tzinfo=UTC_TZ)
                    utc_end_dt = utc_start_dt + timedelta(hours=3)
                    local_start_dt = utc_start_dt.astimezone(target_tz)
                    local_end_dt = utc_end_dt.astimezone(target_tz)
                    high_kp_periods.append((local_start_dt, local_end_dt, kp_index))
            except ValueError:
                continue 
    return high_kp_periods

def send_email_alert(high_kp_periods, local_tz_name_for_display):
    """Sends an email alert if there are high Kp-index periods."""
    if not high_kp_periods:
        print(f"No periods with Kp >= {KP_THRESHOLD} found. No email sent.")
        return

    # Parse the RECIPIENT_STRING into a list of individual email addresses for BCC
    # And ensure the sender is also in the list of who actually receives it.
    bcc_recipients_list = [email.strip() for email in RECIPIENT_STRING.split(',') if email.strip()]
    
    # The list of all addresses the email will actually be sent to
    all_to_addrs = [EMAIL_SENDER] + bcc_recipients_list
    # Remove duplicates just in case sender is also in RECIPIENT_STRING
    all_to_addrs = sorted(list(set(all_to_addrs))) 

    if not all_to_addrs: # Should not happen if EMAIL_SENDER is always present
        print("Error: No valid recipients configured.")
        return

    max_kp_found = max(p[2] for p in high_kp_periods) if high_kp_periods else 0

    subject = f"Aurora Alert! Kp Index Forecast to Reach {max_kp_found}"
    body = (f"High aurora activity is forecasted. Times are displayed in {local_tz_name_for_display}.\n"
            f"Alert triggered for Kp-index of {KP_THRESHOLD} or greater:\n\n")

    high_kp_periods.sort(key=lambda x: x[0])

    for start_dt, end_dt, kp in high_kp_periods:
        time_format = "%a, %b %d, %I:%M %p"
        period_str = (f"{start_dt.strftime(time_format)} to "
                      f"{end_dt.strftime('%I:%M %p %Z')}")
        body += f"- {period_str}, Forecasted Kp-Index: {kp}\n"
    
    body += f"\nThis alert was triggered based on settings for magnetic latitude ~{MAGNETIC_LATITUDE}° and longitude ~{MAGNETIC_LONGITUDE}°."
    body += "\n\nCheck the latest animated forecast at: https://www.swpc.noaa.gov/products/aurora-30-minute-forecast"
    body += "\nRaw 3-day text forecast: https://services.swpc.noaa.gov/text/3-day-forecast.txt"

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_SENDER # Email is addressed visibly To the sender
    # No 'Cc' or 'Bcc' headers are set in the MIME message itself for the BCC recipients
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            # server.send_message(msg) # This might not handle BCCs as intended by some older libraries
            # Using sendmail is more explicit for controlling envelope recipients
            server.sendmail(EMAIL_SENDER, all_to_addrs, msg.as_string())
        print(f"Email alert sent successfully to {EMAIL_SENDER} and BCC'd to {len(bcc_recipients_list)} recipient(s).")
    except smtplib.SMTPException as e:
        print(f"Error sending email: {e}")
        print("Please double-check your SMTP settings, username, and password in the .env file.")
    except Exception as e:
        print(f"An unexpected error occurred during email sending: {e}")

if __name__ == "__main__":
    print("Running Aurora Alert Check...")
    print(f"Fetching and parsing REAL aurora forecast (times will be converted to {LOCAL_TZ_NAME})...")
    forecast_text = get_aurora_forecast()
    if forecast_text:
        high_kp_periods = parse_forecast(forecast_text, LOCAL_TZ)
        send_email_alert(high_kp_periods, LOCAL_TZ_NAME)
    else:
        print("Could not retrieve forecast data. No email sent.")