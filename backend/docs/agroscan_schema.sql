-- AgroScan: esquema SQL de trazabilidad AGROP-29


CREATE TABLE lots (
	id INTEGER NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	product VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	responsible VARCHAR(100) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX ix_lots_code ON lots (code);


CREATE TABLE measurements (
	id INTEGER NOT NULL, 
	device_id VARCHAR(64) NOT NULL, 
	boot_id VARCHAR(64) NOT NULL, 
	seq INTEGER NOT NULL, 
	weight_g FLOAT NOT NULL, 
	stable BOOLEAN NOT NULL, 
	calibration_version VARCHAR(64) NOT NULL, 
	received_at DATETIME NOT NULL, 
	zero_confirmed BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_measurement_seq UNIQUE (device_id, boot_id, seq)
)

;

CREATE INDEX ix_measurements_device_id ON measurements (device_id);


CREATE TABLE pieces (
	id INTEGER NOT NULL, 
	lot_id INTEGER NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_piece_lot_code UNIQUE (lot_id, code), 
	FOREIGN KEY(lot_id) REFERENCES lots (id)
)

;

CREATE INDEX ix_pieces_lot_id ON pieces (lot_id);


CREATE TABLE evaluations (
	id INTEGER NOT NULL, 
	lot_id INTEGER NOT NULL, 
	piece_id VARCHAR(64) NOT NULL, 
	piece_ref_id INTEGER, 
	product VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	weight_grams FLOAT, 
	image_count INTEGER NOT NULL, 
	visual_category VARCHAR(50), 
	review_note VARCHAR(500), 
	calibration_reference VARCHAR(100), 
	model_version VARCHAR(50), 
	rules_version VARCHAR(50), 
	weight_pre_g FLOAT, 
	weight_pre_at DATETIME, 
	weight_post_g FLOAT, 
	weight_post_at DATETIME, 
	weight_pre_measurement_id INTEGER, 
	weight_post_measurement_id INTEGER, 
	device_id VARCHAR(64), 
	boot_id VARCHAR(64), 
	failure_reason VARCHAR(300), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lot_id) REFERENCES lots (id), 
	FOREIGN KEY(piece_ref_id) REFERENCES pieces (id), 
	FOREIGN KEY(weight_pre_measurement_id) REFERENCES measurements (id), 
	FOREIGN KEY(weight_post_measurement_id) REFERENCES measurements (id)
)

;

CREATE INDEX ix_evaluations_lot_id ON evaluations (lot_id);

CREATE INDEX ix_evaluations_piece_ref_id ON evaluations (piece_ref_id);

CREATE INDEX ix_evaluations_piece_id ON evaluations (piece_id);


CREATE TABLE images (
	id INTEGER NOT NULL, 
	evaluation_id INTEGER NOT NULL, 
	"view" VARCHAR(30) NOT NULL, 
	relative_path VARCHAR(300) NOT NULL, 
	content_type VARCHAR(30) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evaluation_id) REFERENCES evaluations (id)
)

;

CREATE INDEX ix_images_evaluation_id ON images (evaluation_id);


CREATE TABLE reviews (
	id INTEGER NOT NULL, 
	evaluation_id INTEGER NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	actor_id VARCHAR(64) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	previous_value VARCHAR(50), 
	updated_value VARCHAR(50), 
	performed_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evaluation_id) REFERENCES evaluations (id)
)

;

CREATE INDEX ix_reviews_evaluation_id ON reviews (evaluation_id);

