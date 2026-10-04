CREATE TABLE service_runtime (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    last_successful_send_at TIMESTAMPTZ
);

INSERT INTO service_runtime(singleton, last_successful_send_at) VALUES (TRUE, NULL);
