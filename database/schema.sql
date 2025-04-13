-- file: new_schema.sql

-- Create the Users table
CREATE TABLE IF NOT EXISTS Users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the Compounds table with molecular properties
CREATE TABLE IF NOT EXISTS Compounds (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES Users(id) NOT NULL,
    name VARCHAR(255) NOT NULL,
    smiles TEXT NOT NULL,
    inchi_key VARCHAR(27),
    chembl_id VARCHAR(20),
    pubchem_cid VARCHAR(20),
    molecular_weight FLOAT,
    tpsa FLOAT,
    hbd INTEGER,
    hba INTEGER,
    num_atoms INTEGER,
    num_heavy_atoms INTEGER,
    num_rotatable_bonds INTEGER,
    num_rings INTEGER,
    qed FLOAT,
    logp FLOAT,
    kingdom VARCHAR(100),
    superclass VARCHAR(100),
    class VARCHAR(100),
    subclass VARCHAR(100),
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the Analysis_Jobs table
CREATE TABLE IF NOT EXISTS Analysis_Jobs (
    id VARCHAR(36) PRIMARY KEY,
    compound_id VARCHAR(36) REFERENCES Compounds(id) NOT NULL,
    user_id VARCHAR(36) REFERENCES Users(id) NOT NULL,
    status TEXT NOT NULL,
    progress FLOAT NOT NULL DEFAULT 0.0,
    similarity_threshold INTEGER NOT NULL DEFAULT 80,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the Compound_Job_Relations table (new table)
CREATE TABLE IF NOT EXISTS Compound_Job_Relations (
    compound_id VARCHAR(36) REFERENCES Compounds(id) NOT NULL,
    job_id VARCHAR(36) REFERENCES Analysis_Jobs(id) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (compound_id, job_id)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_compound_job_relations_job_id ON Compound_Job_Relations(job_id);
CREATE INDEX IF NOT EXISTS idx_compound_job_relations_compound_id ON Compound_Job_Relations(compound_id);
CREATE INDEX IF NOT EXISTS idx_compound_job_relations_is_primary ON Compound_Job_Relations(is_primary);

-- Create additional indexes on frequently queried fields
CREATE INDEX IF NOT EXISTS idx_compounds_user_id ON Compounds(user_id);
CREATE INDEX IF NOT EXISTS idx_compounds_chembl_id ON Compounds(chembl_id);
CREATE INDEX IF NOT EXISTS idx_compounds_inchi_key ON Compounds(inchi_key);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_user_id ON Analysis_Jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON Analysis_Jobs(status);