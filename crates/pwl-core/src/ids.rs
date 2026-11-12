//! Стабильные идентификаторы. Без внешних крейтов: время + pid + счётчик,
//! прогнанные через splitmix64. Коллизии внутри процесса исключены счётчиком,
//! между процессами — nanos и pid.

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn mix(mut x: u64) -> u64 {
    x ^= x >> 30;
    x = x.wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x ^= x >> 27;
    x = x.wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^= x >> 31;
    x
}

pub fn new_id(prefix: &str) -> String {
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0);
    let pid = std::process::id() as u64;
    let seed = nanos ^ (pid << 32) ^ n.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    format!("{prefix}_{:016x}{:04x}", mix(seed), n & 0xffff)
}

/// Детерминированный хеш строки (FNV-1a). Используется для эмблем серверов,
/// чтобы они больше не «крутились» при каждой перерисовке.
pub fn stable_hash(s: &str) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in s.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(0x100_0000_01b3);
    }
    h
}

pub fn now_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn ids_are_unique_and_prefixed() {
        let set: HashSet<String> = (0..10_000).map(|_| new_id("acc")).collect();
        assert_eq!(set.len(), 10_000);
        assert!(set.iter().all(|s| s.starts_with("acc_")));
    }

    #[test]
    fn hash_is_stable() {
        assert_eq!(stable_hash("RU-1"), stable_hash("RU-1"));
        assert_ne!(stable_hash("RU-1"), stable_hash("RU-2"));
    }
}