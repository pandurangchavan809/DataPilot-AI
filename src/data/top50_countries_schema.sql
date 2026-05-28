CREATE TABLE countries (
    country_id INTEGER PRIMARY KEY,
    country_name TEXT NOT NULL,
    capital TEXT NOT NULL,
    continent TEXT NOT NULL,
    population INTEGER,
    gdp REAL,
    currency TEXT,
    official_language TEXT
);

CREATE TABLE economy_stats (
    country_id INTEGER,
    year INTEGER,
    gdp_growth REAL,
    inflation_rate REAL,
    unemployment_rate REAL,
    exports REAL,
    imports REAL,
    FOREIGN KEY(country_id) REFERENCES countries(country_id)
);

CREATE TABLE education_stats (
    country_id INTEGER PRIMARY KEY,
    literacy_rate REAL,
    education_index REAL,
    school_enrollment REAL,
    FOREIGN KEY(country_id) REFERENCES countries(country_id)
);

CREATE TABLE tourism_stats (
    country_id INTEGER PRIMARY KEY,
    tourists_per_year INTEGER,
    tourism_revenue REAL,
    top_destination TEXT,
    FOREIGN KEY(country_id) REFERENCES countries(country_id)
);

CREATE TABLE tech_stats (
    country_id INTEGER PRIMARY KEY,
    internet_users INTEGER,
    ai_startups INTEGER,
    tech_exports REAL,
    mobile_penetration REAL,
    FOREIGN KEY(country_id) REFERENCES countries(country_id)
);
