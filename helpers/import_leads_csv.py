import csv
from io import StringIO

from models.lead import Lead
from typing import TypedDict
from tortoise.exceptions import IntegrityError
from datetime import datetime
from models.file import File
import pandas as pd
from helpers.state import stateandtimezone

class ImportResults(TypedDict):
    successes: int
    errors: int
    duplicates: int
    duplicate_phone_numbers: int


async def import_leads_csv(content: str, file: File) -> ImportResults:
    results = {
        "successes": 0,
        "errors": 0,
        "duplicates": 0,
        "duplicate_phone_numbers": 0,
        "total": 0,
        "error_reasons": set(),
    }
    state = stateandtimezone()
    time_zones = {entry["name"] : entry['zone'] for entry in state}
    
    # Track phone numbers within this CSV file to prevent duplicates
    seen_phone_numbers = set()
    
    try:
       
        df = pd.read_csv(StringIO(content)).fillna("") 
        
        required_columns = ["Internal LeadID", "Phone Number", "Acquisition Date", "First Name", "Last Name" , "State"]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            results["error_reasons"].add(f"Missing required columns: {', '.join(missing_columns)}.")
            results["errors"] += 1
            return results

        df = df.map(lambda x: x.strip() if isinstance(x, str) else str(x) if not pd.isna(x) else "")


        results["total"] = len(df)

        for idx, row in df.iterrows():
            try:
                if not row["Internal LeadID"]:
                    raise ValueError("Missing Internal LeadID.")
                if not row["Phone Number"]:
                    raise ValueError("Missing Phone Number.")
                
                # Check if phone number already exists in this CSV file
                phone_number = row["Phone Number"]
                
                # Ensure phone number has + prefix
                if not phone_number.startswith('+'):
                    phone_number = '+' + phone_number
                
                if phone_number in seen_phone_numbers:
                    results["duplicate_phone_numbers"] += 1
                    results["errors"] += 1
                    results["error_reasons"].add(f"Phone number {phone_number} already exists in this CSV file (row {idx + 1}).")
                    continue
                
                # Add phone number to seen set
                seen_phone_numbers.add(phone_number)
                
                try:
                    date_array = row["Acquisition Date"].strip().split("/")
                    if len(date_array) != 3:
                        raise ValueError("Invalid date format or missing Acquisition Date. Expected MM/DD/YYYY.")
                    if len(date_array[0]) == 1:
                        date_array[0] = f"0{date_array[0]}"
                    if len(date_array[1]) == 1:
                        date_array[1] = f"0{date_array[1]}"
                    if len(date_array[2]) == 2:
                        date_array[2] = f"20{date_array[2]}"
                    acquisition_date = datetime.strptime("/".join(date_array), "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    raise ValueError("Invalid date format or missing Acquisition Date . Expected MM/DD/YYYY.")
                state = row["State"].strip().lower()
                matching_state = next((state_name for state_name in time_zones if state in state_name.lower()), None)
                if matching_state:
                   timezone = time_zones[matching_state]
                else:
                   timezone = None
                await Lead(
                    first_name=row.get("First Name"),
                    last_name=row.get("Last Name"),
                    email=row.get("Email"),
                    add_date=acquisition_date,
                    salesforce_id=row["Internal LeadID"],
                    mobile=phone_number,
                    state=row["State"],
                    timezone=timezone,
                    other_data={"Custom_0": row.get("Custom_0"), "Custom_1": row.get("Custom_1")},
                    file=file,
                ).save()

                results["successes"] += 1

            except ValueError as ve:
                results["errors"] += 1
                print("error_reasons", results["error_reasons"])
                results["error_reasons"].add(str(ve))
            except IntegrityError:
                results["duplicates"] += 1
                results["errors"] += 1
                print("error_reasons", results["errors"])

                results["error_reasons"].add("Duplicate entries detected.")
            except Exception as e:
                results["errors"] += 1
                results["error_reasons"].add(f"Unexpected error in row {idx + 1}: {e}")

    except Exception as e:
        results["errors"] += 1
        results["error_reasons"].add(f"Error reading the file: {e}")

    return results


def humanize_results(results: ImportResults) -> str:
    messages = []

    # Case when no rows are successfully added
    if results["successes"] == 0:
        messages.append(f"Unable to add {results['total']} row{'s' if results['total'] != 1 else ''}.")
        if results["error_reasons"]:
            messages.append("Reasons for failure:")
            messages.extend(f"- {reason}" for reason in results["error_reasons"])
        else:
            messages.append("Their is no record found.")
        return " ".join(messages)

    # Case when at least one row is successfully added
    if results["successes"] > 0:
        messages.append(f"{results['successes']} row{'s' if results['successes'] != 1 else ''} successfully added.")
        if results["errors"] > 0:
            messages.append(f"Unable to add {results['errors']} row{'s' if results['errors'] != 1 else ''}.")
        if results["duplicates"] > 0:
            messages.append(f"Out of which {results['duplicates']} had invalid or duplicate values.")
        if results["duplicate_phone_numbers"] > 0:
            messages.append(f"Out of which {results['duplicate_phone_numbers']} had duplicate phone numbers within the CSV file.")
    
    return " ".join(messages)
