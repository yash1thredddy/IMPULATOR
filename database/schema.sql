-- Create the database (if it doesn't exist)
CREATE DATABASE impulsor_db;


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

-- Create the Compounds table
CREATE TABLE IF NOT EXISTS Compounds (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES Users(id) NOT NULL,
    name VARCHAR(255) NOT NULL,
    smiles TEXT NOT NULL,
    inchi_key VARCHAR(27),
    pubchem_cid VARCHAR(20),
    molecular_weight FLOAT,
    tpsa FLOAT,
    hbd INTEGER,
    hba INTEGER,
    num_atoms INTEGER,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the Activities table
CREATE TABLE IF NOT EXISTS Activities (
    id VARCHAR(36) PRIMARY KEY,
    compound_id VARCHAR(36) REFERENCES Compounds(id),
    target_id VARCHAR(50) NOT NULL,
    standard_type VARCHAR(50) NOT NULL,
    standard_relation VARCHAR(10) NOT NULL,
    standard_value FLOAT NOT NULL,
    standard_units VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the AnalysisJobs table
CREATE TABLE IF NOT EXISTS Analysis_Jobs (
    id VARCHAR(36) PRIMARY KEY,
    compound_id VARCHAR(36) REFERENCES Compounds(id) NOT NULL,
    user_id VARCHAR(36) REFERENCES Users(id) NOT NULL,
    status TEXT NOT NULL,
    progress FLOAT NOT NULL DEFAULT 0.0,
    similarity_threshold INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the Efficiency_Metrics table
CREATE TABLE IF NOT EXISTS Efficiency_Metrics (
    id VARCHAR(36) PRIMARY KEY,
    analysis_job_id VARCHAR(36) REFERENCES Analysis_Jobs(id),
    compound_id VARCHAR(36) REFERENCES Compounds(id),
    sei FLOAT NULL,
    bei FLOAT NULL,
    nsei FLOAT NULL,
    nbei FLOAT NULL,
    llep FLOAT NULL,
    lle FLOAT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);