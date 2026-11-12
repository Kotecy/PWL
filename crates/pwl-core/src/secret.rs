//! Пароли. Ядро не знает про Win32: шифрование отдаётся трейту `Protector`,
//! который на Windows реализован через DPAPI (`CryptProtectData`), а на других
//! ОС и в тестах — через `NoopProtector`.
//!
//! Инвариант: наружу (в UI) пароль не уходит никогда. `AccountView` его не содержит.

use serde::{Deserialize, Serialize};

use crate::error::{Error, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "lowercase")]
pub enum Secret {
    /// Открытый текст. Допустим только на этапе миграции или на не-Windows.
    Plain(String),
    /// DPAPI-блоб в base64. Расшифровать может только тот же пользователь Windows.
    Protected(String),
}

impl Secret {
    pub fn is_empty(&self) -> bool {
        match self {
            Secret::Plain(s) => s.is_empty(),
            Secret::Protected(_) => false,
        }
    }
}

impl Default for Secret {
    fn default() -> Self {
        Secret::Plain(String::new())
    }
}

pub trait Protector: Send + Sync {
    fn protect(&self, plain: &str) -> Result<Secret>;
    fn reveal(&self, secret: &Secret) -> Result<String>;
    /// true, если пароли реально шифруются (UI показывает это в настройках).
    fn is_secure(&self) -> bool;
}

/// Заглушка: хранит как есть. Тесты и не-Windows сборки.
pub struct NoopProtector;

impl Protector for NoopProtector {
    fn protect(&self, plain: &str) -> Result<Secret> {
        Ok(Secret::Plain(plain.to_string()))
    }
    fn reveal(&self, secret: &Secret) -> Result<String> {
        match secret {
            Secret::Plain(s) => Ok(s.clone()),
            Secret::Protected(b64) => {
                let bytes = b64_decode(b64)?;
                String::from_utf8(bytes).map_err(|_| Error::Codec("пароль не UTF-8".into()))
            }
        }
    }
    fn is_secure(&self) -> bool {
        false
    }
}

/// Минимальный base64 (RFC 4648, с padding). Свой, чтобы не тянуть крейт
/// ради 30 строк: меньше зависимостей — быстрее сборка и меньше exe.
pub fn b64_encode(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = chunk.get(1).copied().unwrap_or(0) as u32;
        let b2 = chunk.get(2).copied().unwrap_or(0) as u32;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}

pub fn b64_decode(s: &str) -> Result<Vec<u8>> {
    fn val(c: u8) -> Result<u32> {
        match c {
            b'A'..=b'Z' => Ok((c - b'A') as u32),
            b'a'..=b'z' => Ok((c - b'a' + 26) as u32),
            b'0'..=b'9' => Ok((c - b'0' + 52) as u32),
            b'+' => Ok(62),
            b'/' => Ok(63),
            _ => Err(Error::Codec("некорректный base64".into())),
        }
    }
    let raw: Vec<u8> = s.bytes().filter(|b| !b.is_ascii_whitespace() && *b != b'=').collect();
    let mut out = Vec::with_capacity(raw.len() / 4 * 3 + 3);
    for chunk in raw.chunks(4) {
        if chunk.len() == 1 {
            return Err(Error::Codec("некорректный base64".into()));
        }
        let mut n = 0u32;
        for i in 0..4 {
            n <<= 6;
            n |= chunk.get(i).copied().map(val).transpose()?.unwrap_or(0);
        }
        out.push((n >> 16) as u8);
        if chunk.len() > 2 {
            out.push((n >> 8) as u8);
        }
        if chunk.len() > 3 {
            out.push(n as u8);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_roundtrip_all_lengths() {
        for len in 0..200usize {
            let data: Vec<u8> = (0..len).map(|i| (i * 37 % 256) as u8).collect();
            let enc = b64_encode(&data);
            assert_eq!(b64_decode(&enc).unwrap(), data, "len={len}");
        }
    }

    #[test]
    fn base64_known_vectors() {
        assert_eq!(b64_encode(b""), "");
        assert_eq!(b64_encode(b"f"), "Zg==");
        assert_eq!(b64_encode(b"fo"), "Zm8=");
        assert_eq!(b64_encode(b"foo"), "Zm9v");
        assert_eq!(b64_encode(b"foobar"), "Zm9vYmFy");
        assert_eq!(b64_decode("Zm9vYmFy").unwrap(), b"foobar");
    }

    #[test]
    fn base64_rejects_garbage() {
        assert!(b64_decode("A").is_err());
        assert!(b64_decode("!!!!").is_err());
    }

    #[test]
    fn noop_protector_roundtrip() {
        let p = NoopProtector;
        let s = p.protect("пароль-123").unwrap();
        assert_eq!(p.reveal(&s).unwrap(), "пароль-123");
        assert!(!p.is_secure());
        assert!(Secret::default().is_empty());
    }
}