extern crate rand;
extern crate rand_chacha;
extern crate log;

use sha2::{Sha256, Digest};
use rand::{Rng, SeedableRng, rngs::StdRng};
use rand::distributions::Alphanumeric;

struct ChunkGenerator {
    seed: [u8; 32],
    chunk_size: usize,
    chunk: Vec<u8>
}

impl ChunkGenerator {
    pub fn new(seed: &str, chunk_size: usize) -> Self {
        ChunkGenerator {
            seed: Self::hash_data(seed.as_bytes()),
            chunk_size,
            chunk: vec![0u8; chunk_size]
        }
    }

    fn generate_string_chunk(&self) -> Vec<u8> {
        let prng = StdRng::from_seed(self.seed);
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

    fn xor_operation(base: &[u8], input: &[u8]) -> Vec<u8> {
        base.iter().zip(input.iter())
            .map(|(&a, &b)| a ^ b)
            .collect()
    }

    pub fn next(&mut self) -> (Vec<u8>, [u8; 32]) {
        println!("Current Chunk (Hex): 0x{:?}", hex::encode(&self.chunk));
        println!("Current Seed (Hex): 0x{:?}", hex::encode(&self.seed));

        let base = self.generate_string_chunk();
        println!("Base (Hex): 0x{:?}", hex::encode(&base));

        let new_chunk = Self::xor_operation(&self.chunk, &base);
        println!("Next Chunk (Hex): 0x{:?}", hex::encode(&new_chunk));
        
        let hash = Self::hash_data(&new_chunk);
        println!("Next Seed (Hex): 0x{:?}", hex::encode(&hash));

        self.seed = hash;
        self.chunk = new_chunk.clone();
        
        (new_chunk, hash)
    }
}

fn main() {
    let seed = "test_seed";
    let chunk_size = 10;
    
    let mut chunk_gen = ChunkGenerator::new(seed, chunk_size);
    
    for i in 0..5 {
        println!("========================================");
        println!("Step {}", i);
        println!("----------------------------------------");
        let (_chunk, _hash) = chunk_gen.next();
        println!("========================================");
    }
}