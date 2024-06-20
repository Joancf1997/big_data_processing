-- Granular information for each point
CREATE TABLE point_data (
  time_stamp TIMESTAMP WITH TIME ZONE,
  id VARCHAR, 
  place VARCHAR,
  generation BOOLEAN,
  type_gen VARCHAR,
  kwh DOUBLE PRECISION,
  PRIMARY KEY (time_stamp, place, id)
);

-- Data from the three positions
CREATE TABLE weather_data (
  time_stamp TIMESTAMP WITH TIME ZONE,
  place VARCHAR,
  temp DOUBLE PRECISION, 
  dew_point DOUBLE PRECISION,
  uvi DOUBLE PRECISION,
  clouds DOUBLE PRECISION,
  PRIMARY KEY (time_stamp, place)
);

-- Data from the nergy analysis
CREATE TABLE energy_analytics (
  hour_group TIMESTAMP WITH TIME ZONE,
  kwh_prod DOUBLE PRECISION,
  kwh_cons DOUBLE PRECISION,
  ratio DOUBLE PRECISION,
  PRIMARY KEY (hour_group)
);


CREATE TABLE energy_weather_analytics (
  hour_group TIMESTAMP WITH TIME ZONE,
  place VARCHAR,
  kwh_cons_degree DOUBLE PRECISION,
  kwh_prod_with_rain_prob DOUBLE PRECISION,
  kwh_prod_with_no_rain_prob DOUBLE PRECISION,
  PRIMARY KEY (hour_group)
);
