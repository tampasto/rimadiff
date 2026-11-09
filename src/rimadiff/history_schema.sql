CREATE TABLE User (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, -- Trimmed and lower cased
  display TEXT NOT NULL, -- As in config file
  added_date_ordinal INT NOT NULL -- Python datetime.date ordinal
) STRICT;

CREATE TABLE APICategory (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, -- As in URL model field
  display TEXT NOT NULL
) STRICT;

CREATE TABLE LabelCategory (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, -- As in API key (skills, activities, ...)
  display TEXT NOT NULL
) STRICT;

CREATE TABLE DataCategory (
  id INTEGER PRIMARY KEY,
  label_category INT NOT NULL REFERENCES LabelCategory (id) ON DELETE CASCADE,
  name TEXT NOT NULL, -- As in API key (level, xp, ...)
  display TEXT NOT NULL
) STRICT;

CREATE TABLE Label (
  id INTEGER PRIMARY KEY,
  label_category INT NOT NULL REFERENCES LabelCategory (id) ON DELETE CASCADE,
  name TEXT NOT NULL, -- Trimmed and lower cased
  display TEXT NOT NULL, -- As in API output
  position INT NOT NULL, -- As in API id field
  added_date_ordinal INT NOT NULL -- Python datetime.date ordinal
) STRICT;

CREATE TABLE Snapshot (
  id INTEGER PRIMARY KEY,
  date_ordinal INT NOT NULL, -- Python datetime.date ordinal
  user_id INT NOT NULL REFERENCES User (id) ON DELETE CASCADE,
  api_category INT NOT NULL REFERENCES APICategory (id) ON DELETE CASCADE,
  time TEXT NOT NULL, -- Local time as HH:MM
  timezone TEXT NOT NULL, -- As +HHMM
  url TEXT NOT NULL
) STRICT;

CREATE TABLE Data (
  id INTEGER PRIMARY KEY,
  snapshot INT NOT NULL REFERENCES Snapshot (id) ON DELETE CASCADE,
  label INT NOT NULL REFERENCES Label (id) ON DELETE CASCADE,
  data_category INT NOT NULL REFERENCES DataCategory (id) ON DELETE CASCADE,
  value INT NOT NULL
) STRICT;
