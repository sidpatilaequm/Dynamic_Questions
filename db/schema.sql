-- ============================================================
-- Form Studio — MySQL schema
-- Lives in the SAME database as the rest of the platform (multimedia_governance),
-- not a standalone "form_studio" DB — backend_java reads/writes these tables
-- directly via JPA, the same way WorkFlow already shares that database.
-- Run with:  mysql -u root -p multimedia_governance < db/schema.sql
-- ============================================================

-- ------------------------------------------------------------
-- A process is the top-level container: an onboarding flow,
-- an audit, a vendor intake. It owns sections, which own questions.
--
-- external_key lets another service (backend_java) look up "the currently
-- active questionnaire for X" without a hardcoded numeric process id, e.g.
-- WHERE external_key = 'become_a_supplier' AND status = 'published'. At most
-- one process holds a given key at a time.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processes (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(200)  NOT NULL,
  description  TEXT          NULL,
  status       ENUM('draft', 'published', 'closed') NOT NULL DEFAULT 'draft',
  external_key VARCHAR(100)  NULL,
  created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_processes_external_key (external_key)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- Sections group questions and carry their own order within a process.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sections (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  process_id   INT           NOT NULL,
  title        VARCHAR(200)  NOT NULL,
  description  TEXT          NULL,
  position     INT           NOT NULL DEFAULT 0,
  CONSTRAINT fk_sections_process
    FOREIGN KEY (process_id) REFERENCES processes (id) ON DELETE CASCADE,
  KEY idx_sections_order (process_id, position)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- Questions. `position` is the order inside the section, so moving a
-- question between sections is just a section_id + position rewrite.
--
--   short_text     free text answer          -> answers.text_value
--   single_choice  pick exactly one option   -> one row in answer_options
--                  (is_dropdown: render as <select> instead of radio buttons)
--   multi_choice   pick one or more options  -> N rows in answer_options
--   counter        a bounded integer         -> answers.text_value (stringified)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS questions (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  section_id      INT           NOT NULL,
  prompt          TEXT          NOT NULL,
  help_text       VARCHAR(500)  NULL,
  question_type   ENUM('short_text', 'single_choice', 'multi_choice', 'counter', 'table') NOT NULL,
  is_mandatory    TINYINT(1)    NOT NULL DEFAULT 0,
  position        INT           NOT NULL DEFAULT 0,
  max_length      INT           NULL,  -- short_text only
  min_selections  INT           NULL,  -- multi_choice only
  max_selections  INT           NULL,  -- multi_choice only
  is_dropdown     TINYINT(1)    NOT NULL DEFAULT 0,  -- single_choice only
  min_value       INT           NULL,  -- counter only
  max_value       INT           NULL,  -- counter only
  min_rows        INT           NULL,  -- table only
  max_rows        INT           NULL,  -- table only
  CONSTRAINT fk_questions_section
    FOREIGN KEY (section_id) REFERENCES sections (id) ON DELETE CASCADE,
  KEY idx_questions_order (section_id, position)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- Choices offered by single_choice / multi_choice questions.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS question_options (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  question_id  INT           NOT NULL,
  label        VARCHAR(300)  NOT NULL,
  position     INT           NOT NULL DEFAULT 0,
  CONSTRAINT fk_options_question
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
  KEY idx_options_order (question_id, position)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- Column definitions for table-type questions. The respondent fills in one
-- row at a time; each row supplies a value per column (see answers.table_rows).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS question_columns (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  question_id   INT            NOT NULL,
  label         VARCHAR(300)   NOT NULL,
  column_type   ENUM('text', 'number', 'date') NOT NULL DEFAULT 'text',
  is_required   TINYINT(1)     NOT NULL DEFAULT 0,
  position      INT            NOT NULL DEFAULT 0,
  CONSTRAINT fk_columns_question
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
  KEY idx_columns_order (question_id, position)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- One row per completed submission of a process.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS responses (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  process_id        INT           NOT NULL,
  respondent_name   VARCHAR(200)  NULL,
  respondent_email  VARCHAR(200)  NULL,
  submitted_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_responses_process
    FOREIGN KEY (process_id) REFERENCES processes (id) ON DELETE CASCADE,
  KEY idx_responses_process (process_id, submitted_at)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- One row per answered question. text_value holds short_text/counter
-- answers; choice answers hang off answer_options below; table_rows holds
-- table-type answers as a JSON list of {column_id (as string): cell value}.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS answers (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  response_id  INT   NOT NULL,
  question_id  INT   NOT NULL,
  text_value   TEXT  NULL,
  table_rows   JSON  NULL,
  CONSTRAINT fk_answers_response
    FOREIGN KEY (response_id) REFERENCES responses (id) ON DELETE CASCADE,
  CONSTRAINT fk_answers_question
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
  UNIQUE KEY uq_answer_per_question (response_id, question_id)
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- Selected options. Single-choice answers have exactly one row here,
-- multi-choice answers have as many as the respondent ticked.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS answer_options (
  answer_id  INT NOT NULL,
  option_id  INT NOT NULL,
  PRIMARY KEY (answer_id, option_id),
  CONSTRAINT fk_answer_options_answer
    FOREIGN KEY (answer_id) REFERENCES answers (id) ON DELETE CASCADE,
  CONSTRAINT fk_answer_options_option
    FOREIGN KEY (option_id) REFERENCES question_options (id) ON DELETE CASCADE
) ENGINE = InnoDB;

-- ------------------------------------------------------------
-- Sample data: one small process you can open straight away.
-- ------------------------------------------------------------
INSERT INTO processes (name, description, status)
SELECT 'Vendor onboarding', 'Collected before a new supplier is added to the payment system.', 'published'
WHERE NOT EXISTS (SELECT 1 FROM processes WHERE name = 'Vendor onboarding');

SET @p := (SELECT id FROM processes WHERE name = 'Vendor onboarding' LIMIT 1);

INSERT INTO sections (process_id, title, description, position)
SELECT @p, 'Company details', 'Legal identity of the supplier.', 0
WHERE NOT EXISTS (SELECT 1 FROM sections WHERE process_id = @p AND position = 0);

INSERT INTO sections (process_id, title, description, position)
SELECT @p, 'Compliance', 'Answers here are reviewed by the risk team.', 1
WHERE NOT EXISTS (SELECT 1 FROM sections WHERE process_id = @p AND position = 1);

SET @s1 := (SELECT id FROM sections WHERE process_id = @p AND position = 0 LIMIT 1);
SET @s2 := (SELECT id FROM sections WHERE process_id = @p AND position = 1 LIMIT 1);

INSERT INTO questions (section_id, prompt, help_text, question_type, is_mandatory, position)
SELECT @s1, 'Registered company name', 'Exactly as it appears on the certificate of incorporation.', 'short_text', 1, 0
WHERE NOT EXISTS (SELECT 1 FROM questions WHERE section_id = @s1 AND position = 0);

INSERT INTO questions (section_id, prompt, help_text, question_type, is_mandatory, position)
SELECT @s1, 'Primary country of operation', NULL, 'single_choice', 1, 1
WHERE NOT EXISTS (SELECT 1 FROM questions WHERE section_id = @s1 AND position = 1);

INSERT INTO questions (section_id, prompt, help_text, question_type, is_mandatory, position)
SELECT @s2, 'Which certifications does the company hold?', 'Tick every one that is current.', 'multi_choice', 0, 0
WHERE NOT EXISTS (SELECT 1 FROM questions WHERE section_id = @s2 AND position = 0);

SET @q2 := (SELECT id FROM questions WHERE section_id = @s1 AND position = 1 LIMIT 1);
SET @q3 := (SELECT id FROM questions WHERE section_id = @s2 AND position = 0 LIMIT 1);

INSERT INTO question_options (question_id, label, position)
SELECT * FROM (
  SELECT @q2 AS q, 'India' AS l, 0 AS p UNION ALL
  SELECT @q2, 'Singapore', 1 UNION ALL
  SELECT @q2, 'United Kingdom', 2 UNION ALL
  SELECT @q2, 'Elsewhere', 3
) AS seed
WHERE NOT EXISTS (SELECT 1 FROM question_options WHERE question_id = @q2);

INSERT INTO question_options (question_id, label, position)
SELECT * FROM (
  SELECT @q3 AS q, 'ISO 9001' AS l, 0 AS p UNION ALL
  SELECT @q3, 'ISO 27001', 1 UNION ALL
  SELECT @q3, 'SOC 2 Type II', 2
) AS seed
WHERE NOT EXISTS (SELECT 1 FROM question_options WHERE question_id = @q3);
