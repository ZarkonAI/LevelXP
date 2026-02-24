-- workouts history/actions migration
ALTER TABLE workouts
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'done',
    ADD COLUMN IF NOT EXISTS source_workout_id bigint NULL REFERENCES workouts(id);

CREATE INDEX IF NOT EXISTS idx_workouts_user_id ON workouts(user_id);
CREATE INDEX IF NOT EXISTS idx_workouts_workout_date ON workouts(workout_date);
