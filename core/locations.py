"""Location expansion for state-level search queries.

When a search_queries entry has a location like "Oregon" or "OR" (a state
name or 2-letter code), expand it into multiple per-metro queries using the
user-defined state→cities mapping stored in the settings table under the
key 'state_metros'.

Mapping shape (stored as JSON in settings):
    {
        "OR": ["Portland", "Eugene", "Salem"],
        "WA": ["Seattle", "Tacoma", "Spokane"]
    }

When dispatching, "Portland" with state_code "OR" becomes "Portland, OR" —
the state code is appended so job sites disambiguate Portland OR from
Portland ME.

If a state code has no mapping defined, the original input passes through
unchanged (job sites typically handle state-only natively).
"""

# 50 states + DC. Order matters — dropdown is alpha by name.
US_STATES = [
    ("AL", "Alabama"),       ("AK", "Alaska"),        ("AZ", "Arizona"),
    ("AR", "Arkansas"),      ("CA", "California"),    ("CO", "Colorado"),
    ("CT", "Connecticut"),   ("DE", "Delaware"),      ("DC", "District of Columbia"),
    ("FL", "Florida"),       ("GA", "Georgia"),       ("HI", "Hawaii"),
    ("ID", "Idaho"),         ("IL", "Illinois"),      ("IN", "Indiana"),
    ("IA", "Iowa"),          ("KS", "Kansas"),        ("KY", "Kentucky"),
    ("LA", "Louisiana"),     ("ME", "Maine"),         ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"),      ("MN", "Minnesota"),
    ("MS", "Mississippi"),   ("MO", "Missouri"),      ("MT", "Montana"),
    ("NE", "Nebraska"),      ("NV", "Nevada"),        ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),    ("NM", "New Mexico"),    ("NY", "New York"),
    ("NC", "North Carolina"),("ND", "North Dakota"),  ("OH", "Ohio"),
    ("OK", "Oklahoma"),      ("OR", "Oregon"),        ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),  ("SC", "South Carolina"),("SD", "South Dakota"),
    ("TN", "Tennessee"),     ("TX", "Texas"),         ("UT", "Utah"),
    ("VT", "Vermont"),       ("VA", "Virginia"),      ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"),     ("WY", "Wyoming"),
]

# Build lookup tables once at import.
_STATE_NAME_TO_CODE = {name.lower(): code for code, name in US_STATES}
_STATE_CODES = {code for code, _ in US_STATES}


def detect_state(location_input):
    """Return the 2-letter state code if location_input is a US state name or
    code, otherwise None.

    Recognizes:
      - 2-letter codes (case-insensitive): "OR", "or"
      - Full names (case-insensitive): "Oregon", "OREGON"

    Returns None for city+state ("Portland, OR") and free text ("Remote") —
    these pass through to the scraper as single searches, unchanged. None
    here means "no state-level expansion needed," not an error.
    """
    if not location_input:
        return None
    s = location_input.strip()
    if not s or ',' in s:
        return None
    if len(s) == 2 and s.upper() in _STATE_CODES:
        return s.upper()
    if s.lower() in _STATE_NAME_TO_CODE:
        return _STATE_NAME_TO_CODE[s.lower()]
    return None


def expand_state_query(location_input, state_metros=None):
    """Return a list of location strings to dispatch as separate searches.

    Args:
        location_input: raw location string from a search_queries entry.
        state_metros: dict mapping state code → list of city names.
                      If None, passes input through unchanged.

    Returns:
        List of location strings. For a state with a defined mapping,
        returns one string per city ("Portland, OR", "Eugene, OR", ...).
        Otherwise returns [location_input] unchanged.

    Examples:
        expand_state_query("Portland, OR", {...}) -> ["Portland, OR"]
        expand_state_query("Oregon", {"OR": ["Portland", "Eugene"]})
            -> ["Portland, OR", "Eugene, OR"]
        expand_state_query("Oregon", {})       -> ["Oregon"]   # no mapping
        expand_state_query("Remote", {...})    -> ["Remote"]   # not a state
    """
    if state_metros is None:
        state_metros = {}
    code = detect_state(location_input)
    if code and code in state_metros and state_metros[code]:
        cities = state_metros[code]
        return [f"{city.strip()}, {code}" for city in cities if city.strip()]
    return [location_input]
