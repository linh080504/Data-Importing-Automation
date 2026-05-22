from __future__ import annotations

def build_field_instructions(country: str | None = None, location_code: int | None = None) -> str:
    """
    Builds dynamic extraction and judgment rules based on the user's specific script,
    adapting to the selected country and location code.
    """
    safe_country = country.strip() if country else "Unknown"
    
    # Simple currency mapping logic based on country
    currency_code = "Local Currency"
    if safe_country.lower() in ("india",):
        currency_code = "INR"
    elif safe_country.lower() in ("vietnam", "viet nam"):
        currency_code = "VND"
    elif safe_country.lower() in ("australia",):
        currency_code = "AUD"
    elif safe_country.lower() in ("united kingdom", "uk"):
        currency_code = "GBP"

    location_str = str(location_code) if location_code else "[Lookup Country Code]"

    return f"""
STRICT VALIDATION AND FORMATTING RULES:
1. **Global Rank**
- Column: `global_rank`
- Leave **COMPLETELY EMPTY** (null) unless you have a verified pure number like `150`.
- Do NOT put text like "A Grade", "NAAC A", etc. That will crash the system.

2. **Numeric Fields**
These columns must contain **ONLY DIGITS / INTEGERS** in the JSON output (no quotes, no spaces, no symbols):
- `location`: For {safe_country}, ALWAYS use exactly `{location_str}` (as a JSON integer).
- `number_of_students`: Realistic integer estimate (e.g. 1500). No text or suffix.
- `international_student_ratio`: 0 for local colleges, or specific ratio percentage integer.
- `sponsored`: 0 or 1
- `student_loan_available`: 0 or 1
- `housing_availability`: 0 or 1
- `immigration_support`: 0 or 1
- `university_campuses`: Number of campuses (integer)

3. **ID Column**
- Column: `id`
- Always return as **null** or blank.

4. **Name / Description**
- `name` must start with: `"[College Name], {safe_country}"`
  Example: `"CHMM College Varkala, {safe_country}"`
- `description` must be a concise, factual single sentence containing: affiliation, founding year (if known), programs offered, and physical location.
  Example: `"Self-financing college affiliated to University of Kerala, established 1995 by Muslim Educational Trust. Offers BCA, BBA, B.Com, B.Sc. Located in Chavarcode, Varkala."`

5. **Financials**
- Column: `financials`
- Format strictly as: `"{currency_code} Amount ($USD Amount in brackets)"`
- You MUST check search/text details for real tuition fees, then convert to approximate USD.
- Examples:
  - `"{currency_code} 54k-1.13L ($650-1360)"`
  - `"{currency_code} 54k-75k ($650-900)"`
  - `"{currency_code} 3L-8L ($3600-9600)"`
- If no concrete tuition fee amount or range is known or inferred, return null.

6. **Campus Student Life**
- Column: `campus_student_life`
- Short, comma-separated list of real facilities/amenities.
- Example: `"25-acre campus, playgrounds, labs, library, Wi-Fi, canteen."`

7. **Student to Faculty Ratio**
- Column: `student_to_faculty_ratio`
- Plain integer only. Example: `12` (meaning 1:12). No text, no colon format.

8. **Phones**
- Column: `admissions_phone`
- Always use international format with country code, no spaces around `+`:
  Example: `+917025176777`

9. **Contact Person**
- Column: `contact_person`
- Leave **null** (blank) unless explicitly known.

10. **Admissions Page Link**
- Column: `admissions_page_link`
- Use the college's real contact or admissions page URL. If no specific admissions page exists, use the homepage URL.
"""

