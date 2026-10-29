CREATE TABLE Label (
  category INT, -- {category_comment}
  id INT,
  version INT,
  value TEXT NOT NULL,
  added_date_ordinal INT NOT NULL,
  PRIMARY KEY (category, id, version)
) STRICT, WITHOUT ROWID;

CREATE TABLE User (
  id INT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE, -- Always lower case
  name_original TEXT, -- Case as in config file
  added_date_ordinal INT NOT NULL
) STRICT, WITHOUT ROWID;

CREATE TABLE UserDataRequest (
  date_ordinal INT, -- Proleptic Gregorian ordinal, 0001-01-01 is 1, etc.
  user_id INT REFERENCES User (id) ON DELETE CASCADE,
  time TEXT NOT NULL, -- Local time as HH:MM
  timezone TEXT NOT NULL, -- As +HHMM
  url TEXT NOT NULL,
  PRIMARY KEY (date_ordinal, user_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE UserData (
  date_ordinal INT,
  user_id INT,
  label_category INT,
  label_id INT,
  label_version INT NOT NULL,
  value INT NOT NULL,
  PRIMARY KEY (date_ordinal, user_id, label_category, label_id),
  FOREIGN KEY (date_ordinal, user_id)
    REFERENCES UserDataRequest (date_ordinal, user_id) ON DELETE CASCADE,
  FOREIGN KEY (label_category, label_id, label_version)
    REFERENCES Label (category, id, version) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

