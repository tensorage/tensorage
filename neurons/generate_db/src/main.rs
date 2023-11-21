extern crate rand;
extern crate rand_chacha;
extern crate indicatif;
extern crate clap;
extern crate rusqlite;
extern crate log;

use rusqlite::{Connection, params};
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use clap::{App, Arg};
use sha2::{Sha256, Digest};
use rand::{Rng, SeedableRng, rngs::StdRng};
use rand::distributions::Alphanumeric;

struct ChunkGenerator {
    seed: [u8; 32],
    chunk_size: usize
}

impl ChunkGenerator {
    pub fn new(seed: [u8; 32], chunk_size: usize) -> Self {
        ChunkGenerator {
            seed,
            chunk_size
        }
    }

    fn generate_string_chunk(&self, seed: [u8; 32]) -> Vec<u8> {
        let prng = StdRng::from_seed(seed);
        prng.sample_iter(Alphanumeric)
            .take(self.chunk_size)
            .map(|char| char as u8)
            .collect()
    }

    fn hash_data(data: &[u8]) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(data);
        hasher.finalize().into()
    }

    // fn xor_operation(base: &[u8], input: &[u8]) -> Vec<u8> {
    //     base.iter().zip(input.iter())
    //         .map(|(&a, &b)| a ^ b)
    //         .collect()
    // }

    pub fn next(&mut self) -> (Vec<u8>, [u8; 32]) {
        // println!("Current Chunk (Hex): 0x{:?}", hex::encode(&self.chunk));
        // println!("Current Seed (Hex): 0x{:?}", hex::encode(&self.seed));

        let mut base = self.generate_string_chunk(self.seed);
        let hash_base = Self::hash_data(&base);
        base.extend(hex::encode(&hash_base).into_bytes());
        // let doubled_base = self.generate_string_chunk(hash_base);
        // // println!("Base (Hex): 0x{:?}", hex::encode(&base));

        // let new_chunk = Self::xor_operation(&doubled_base, &base);
        // // println!("Next Chunk (Hex): 0x{:?}", hex::encode(&new_chunk));
        
        // let hash = Self::hash_data(&new_chunk);
        // // println!("Next Seed (Hex): 0x{:?}", hex::encode(&hash));

        let hash = Self::hash_data(&base);
        self.seed = hash;

        (base, hash)
    }
}

fn main() {
    let matches = App::new("SQLite Chunk Generator")
        .arg(Arg::with_name("path")
            .long("path")
            .value_name("DB_PATH")
            .help("Path to the SQLite database")
            .required(true)
            .takes_value(true))
        .arg(Arg::with_name("hash")
            .long("hash")
            .value_name("hash")
            .help("Stores the hashes instead of the data itself.")
            .required(false)
            .takes_value(false))
        .arg(Arg::with_name("n")
            .long("n")
            .value_name("NUM_CHUNKS")
            .help("Number of chunks to generate")
            .required(true)
            .takes_value(true))
        .arg(Arg::with_name("size")
            .long("size")
            .value_name("CHUNK_SIZE")
            .help("Size of each chunk in bytes")
            .required(true)
            .takes_value(true))
        .arg(Arg::with_name("seed")
            .long("seed")
            .value_name("seed")
            .help("Seed used to generate the data.")
            .required(true)
            .takes_value(true))
        .arg(Arg::with_name("delete")
            .long("delete")
            .help("Delete the table if it exists.")
            .required(false)
            .takes_value(false))
        .get_matches();

    env_logger::init();

    let hash = matches.is_present("hash");
    let path = matches.value_of("path").unwrap();
    let num_chunks: usize = matches.value_of("n").unwrap().parse().expect("Failed to parse number of chunks");
    let chunk_size: usize = matches.value_of("size").unwrap().parse().expect("Failed to parse chunk size");

    // Create a new SQLite connection
    let conn = Connection::open(path).expect("Failed to open database");
    let _result = conn.execute("PRAGMA journal_mode=WAL", params![]);
    let seed_value = matches.value_of("seed").unwrap();
    
    if matches.is_present("delete") {
        let mut delete_table = format!(
            "DROP TABLE IF EXISTS DB{}", 
            seed_value
        );
        conn.execute(&delete_table, params![]).expect("Failed to drop table");
        delete_table = format!(
            "DROP TABLE IF EXISTS latest_rng_state"
        );
        conn.execute(&delete_table, params![]).expect("Failed to drop table");
    }

    let create_table_sql = format!(
        "CREATE TABLE IF NOT EXISTS DB{} (
            id INTEGER PRIMARY KEY, 
            data TEXT NOT NULL, 
            hash TEXT NOT NULL,
            flag TEXT NOT NULL,
            rng_state BLOB NOT NULL
        )", seed_value);
    //log::info!("create_table_sql: {}", create_table_sql);
    conn.execute(&create_table_sql, params![]).expect("Failed to create DB table");

    // Sanitize the seed value to ensure it's safe to use as a table name
    if !seed_value.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
        panic!("Invalid characters in seed value.");
    }
    
    // Set up the progress bar.
    let multi = MultiProgress::new();
    let pb = multi.add(ProgressBar::new(num_chunks as u64));
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} ({eta})")
        .progress_chars("#>-"));

    // This spawns a new thread for the progress bars
    let _progress_thread_handle = std::thread::spawn(move || {
        multi.join().unwrap();
    });

    // Get current state
    //log::info!("Preparing statement to fetch the latest RNG state from the database.");
    
    let mut start_index = 0;
    let chunk = vec![0u8; chunk_size];
    let mut current_seed = ChunkGenerator::hash_data(&chunk);
    
    let query_latest_rng_state = format!("SELECT id, rng_state FROM DB{} ORDER BY id DESC LIMIT 1", seed_value);
    {
        let mut stmt = conn.prepare(&query_latest_rng_state).expect("Failed to prepare statement");

        //log::info!("Executing query to fetch the latest RNG state.");
        let mut rows = stmt.query(params![]).expect("Failed to query database");


        if let Some(row) = rows.next().expect("Failed to read row") {
            start_index = row.get::<_, i64>(0).expect("Failed to get id") as usize + 1;  // +1 because we want to start from the next index
            //log::info!("Found latest id: {}", start_index - 1 );  // subtracting 1 to get the actual latest id

            let seed_as_vec: Vec<u8> = row.get(1).expect("Failed to get rng_state");
            current_seed.copy_from_slice(&seed_as_vec);
            //log::info!("Retrieved RNG state for id: {} seed: {:?}", start_index - 1 , current_seed);
        } else {
            //log::warn!("No RNG state found in the database. Using default seed.");
        }
    }
    
    // Initialize ChunkGenerator with the provided seed and chunk size
    let mut chunk_gen = ChunkGenerator::new(current_seed, chunk_size);

    // Delete excess rows
    if start_index > num_chunks {
        let delete_rows = format!(
            "DELETE FROM DB{} WHERE id >= ?", 
            seed_value
        );
        //log::info!("Deleting excess rows up to id: {}", num_chunks);
        conn.execute(&delete_rows, params![num_chunks as i64]).expect("Failed to delete excess rows");
    } else {
        // Generate and store chunks
        pb.inc(start_index as u64);
        for i in start_index..num_chunks {
            let (chunk_data, chunk_hash) = chunk_gen.next();
            let hash_hex = hex::encode(&chunk_hash);

            // Store the id, data, hash, and rng_state
            let insert_sql = format!(
                "INSERT INTO DB{} (id, data, hash, flag, rng_state) VALUES (?, ?, ?, ?, ?)", 
                seed_value
            );

            // Optionally only store the data hash
            // log::info!("Set in DB id: {} seed: {:?}", i, chunk_gen.seed.to_vec());

            if hash {
                // Store only the hash.
                conn.execute(
                    &insert_sql, 
                    params![i as i64, "", hash_hex, "F", chunk_gen.seed.to_vec()]
                ).expect("Failed to insert into database");
            } else {
                // Store all the data.
                conn.execute(
                    &insert_sql, 
                    params![i as i64, chunk_data, hash_hex, "F", chunk_gen.seed.to_vec()]
                ).expect("Failed to insert into database");
            }
            pb.inc(1);
        };
        pb.finish();

        // Get current state
        //log::info!("Finish");

        // Wait for the progress bars to finish
        _progress_thread_handle.join().unwrap();
    }
    if let Err(err) = conn.close() {
        eprintln!("Error closing the database connection: {:?}", err);
    }
}