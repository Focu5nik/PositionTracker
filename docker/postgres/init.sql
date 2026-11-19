\getenv monolith_db MONOLITH_DB_NAME
\getenv monolith_user MONOLITH_DB_USER
\getenv monolith_password MONOLITH_DB_PASSWORD
\getenv tracker_db TRACKER_DB_NAME
\getenv tracker_user TRACKER_DB_USER
\getenv tracker_password TRACKER_DB_PASSWORD

CREATE ROLE :"monolith_user" LOGIN PASSWORD :'monolith_password';
CREATE ROLE :"tracker_user" LOGIN PASSWORD :'tracker_password';

CREATE DATABASE :"monolith_db" OWNER :"monolith_user";
CREATE DATABASE :"tracker_db" OWNER :"tracker_user";

REVOKE ALL ON DATABASE :"monolith_db" FROM PUBLIC;
REVOKE ALL ON DATABASE :"tracker_db" FROM PUBLIC;
