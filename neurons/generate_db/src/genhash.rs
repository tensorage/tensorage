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

fn hash_data(data: [u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hasher.finalize().into()
}

fn generate_hash(seed, chunk_size) {
    let mut base = StdRng::from_seed(seed);
    base.sample_iter(Alphanumeric)
        .take(chunk_size)
        .map(|char| char as u8)
        .collect();

    let hash_base = hash_data(base);
    base.extend(hex::encode(&hash_base).into_bytes());

    let hash = hash_data(base);
    (base, hash)
}

fn multiple_generate_hash(start_index:usize, num_chunks:usize, chunk_size:usize) {
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

    let chunk = vec![0u8; chunk_size];
    let mut current_seed = hash_data(chunk);

    pb.inc(start_index as u64);
    for i in start_index..num_chunks {
        let (chunk_data, chunk_hash) = generate_hash(current_seed, chunk_size);
        current_seed = chunk_hash
    }
    pb.inc(1);
    pb.finish();
    _progress_thread_handle.join().unwrap();

    // Return the final value of current_seed
    current_seed
}

fn main() {
    let matches = App::new("Chunk Generator")
        .arg(Arg::with_name("start_index")
            .long("start_index")
            .value_name("START_INDEX")
            .help("Number of start_index")
            .required(true)
            .takes_value(true))
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
        .get_matches();

    env_logger::init();

    let start_index: usize = matches.value_of("start_index").unwrap().parse().expect("Failed to parse number of start_index");
    let num_chunks: usize = matches.value_of("n").unwrap().parse().expect("Failed to parse number of chunks");
    let chunk_size: usize = matches.value_of("size").unwrap().parse().expect("Failed to parse chunk size");

    let match_hash = multiple_generate_hash(start_index, num_chunks, chunk_size)

    println!(match_hash);
