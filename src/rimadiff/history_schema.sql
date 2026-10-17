CREATE TABLE Label (
  category INT, -- 0: Skill level, 1: Skill xp, 2: Skill rank, 3: Activity, 4: Activity rank
  id INT,
  version INT,
  value TEXT NOT NULL,
  PRIMARY KEY (category, id, version)
) STRICT, WITHOUT ROWID;

CREATE TABLE User (
  id INT PRIMARY KEY,
  user TEXT NOT NULL UNIQUE,
  official_name TEXT
) STRICT, WITHOUT ROWID;

CREATE TABLE UserDataTime (
  date_ordinal INT,
  user_id INT REFERENCES User (id) ON DELETE CASCADE,
  time TEXT NOT NULL, -- Local time as HH:MM
  timezone TEXT NOT NULL, -- As +HHMM
  PRIMARY KEY (date_ordinal, user_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE UserData (
  date_ordinal INT, -- Proleptic Gregorian ordinal, 0001-01-01 is 1, etc.
  user_id INT,
  label_category INT,
  label_id INT,
  label_version INT NOT NULL,
  value INT NOT NULL,
  PRIMARY KEY (date_ordinal, user_id, label_category, label_id),
  FOREIGN KEY (date_ordinal, user_id)
    REFERENCES UserDataTime (date_ordinal, user_id) ON DELETE CASCADE,
  FOREIGN KEY (label_category, label_id, label_version)
    REFERENCES Label (category, id, version) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

