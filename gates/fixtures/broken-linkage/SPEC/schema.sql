-- 本地单文件 SQLite 结构（S4 产出）
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE TaskModel (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL DEFAULT '',
  dueDate    TEXT,
  dueTime    INTEGER DEFAULT 540 CHECK (dueTime BETWEEN 0 AND 1439),
  allDay     INTEGER NOT NULL DEFAULT 0 CHECK (allDay IN (0, 1)),
  repeat     TEXT CHECK (repeat IN ('NONE', 'WEEKLY', 'WORKDAYS', 'CUSTOM')),
  byday      TEXT,
  revision   INTEGER NOT NULL DEFAULT 1,
  updatedAt  TEXT NOT NULL
);

CREATE TABLE Reminder (
  id       TEXT PRIMARY KEY,
  taskId   TEXT NOT NULL REFERENCES TaskModel(id) ON DELETE CASCADE,
  fireAt   TEXT NOT NULL,
  state    TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'fired', 'cancelled'))
);

CREATE INDEX idx_task_due ON TaskModel(dueDate);
CREATE INDEX idx_reminder_task ON Reminder(taskId);
