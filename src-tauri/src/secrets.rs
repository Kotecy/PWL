//! Защита паролей. На Windows — DPAPI (`CryptProtectData`): ключ привязан к
//! учётной записи пользователя, никаких мастер-паролей и внешних крейтов.
//!
//! FFI объявлен вручную: крейт `windows` тянет сотни килобайт кода и минуты
//! сборки ради двух функций. Здесь — две структуры и три extern-объявления.

use std::sync::Arc;

use pwl_core::secret::{b64_decode, b64_encode};
use pwl_core::{Error, Protector, Result, Secret};

#[cfg(windows)]
pub fn platform_protector() -> Arc<dyn Protector> {
    Arc::new(Dpapi)
}

#[cfg(not(windows))]
pub fn platform_protector() -> Arc<dyn Protector> {
    Arc::new(pwl_core::NoopProtector)
}

#[cfg(windows)]
mod ffi {
    use std::ffi::c_void;

    #[repr(C)]
    pub struct Blob {
        pub cb_data: u32,
        pub pb_data: *mut u8,
    }

    #[link(name = "crypt32")]
    extern "system" {
        pub fn CryptProtectData(
            data_in: *const Blob,
            descr: *const u16,
            entropy: *const Blob,
            reserved: *const c_void,
            prompt: *const c_void,
            flags: u32,
            data_out: *mut Blob,
        ) -> i32;

        pub fn CryptUnprotectData(
            data_in: *const Blob,
            descr: *mut *const u16,
            entropy: *const Blob,
            reserved: *const c_void,
            prompt: *const c_void,
            flags: u32,
            data_out: *mut Blob,
        ) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        pub fn LocalFree(mem: *mut c_void) -> *mut c_void;
    }

    pub const CRYPTPROTECT_UI_FORBIDDEN: u32 = 0x01;
}

#[cfg(windows)]
struct Dpapi;

#[cfg(windows)]
impl Dpapi {
    fn crypt(input: &[u8], protect: bool) -> Result<Vec<u8>> {
        use std::ptr;

        let in_blob = ffi::Blob {
            cb_data: input.len() as u32,
            pb_data: input.as_ptr() as *mut u8,
        };
        let mut out_blob = ffi::Blob { cb_data: 0, pb_data: ptr::null_mut() };

        let ok = unsafe {
            if protect {
                ffi::CryptProtectData(
                    &in_blob,
                    ptr::null(),
                    ptr::null(),
                    ptr::null(),
                    ptr::null(),
                    ffi::CRYPTPROTECT_UI_FORBIDDEN,
                    &mut out_blob,
                )
            } else {
                ffi::CryptUnprotectData(
                    &in_blob,
                    ptr::null_mut(),
                    ptr::null(),
                    ptr::null(),
                    ptr::null(),
                    ffi::CRYPTPROTECT_UI_FORBIDDEN,
                    &mut out_blob,
                )
            }
        };

        if ok == 0 {
            return Err(Error::Codec(format!(
                "DPAPI: {}",
                std::io::Error::last_os_error()
            )));
        }
        let bytes = unsafe {
            let slice = std::slice::from_raw_parts(out_blob.pb_data, out_blob.cb_data as usize);
            let owned = slice.to_vec();
            ffi::LocalFree(out_blob.pb_data as *mut std::ffi::c_void);
            owned
        };
        Ok(bytes)
    }
}

#[cfg(windows)]
impl Protector for Dpapi {
    fn protect(&self, plain: &str) -> Result<Secret> {
        if plain.is_empty() {
            return Ok(Secret::Plain(String::new()));
        }
        let blob = Self::crypt(plain.as_bytes(), true)?;
        Ok(Secret::Protected(b64_encode(&blob)))
    }

    fn reveal(&self, secret: &Secret) -> Result<String> {
        match secret {
            Secret::Plain(s) => Ok(s.clone()),
            Secret::Protected(b64) => {
                let blob = b64_decode(b64)?;
                let bytes = Self::crypt(&blob, false)?;
                String::from_utf8(bytes)
                    .map_err(|_| Error::Codec("пароль повреждён".into()))
            }
        }
    }

    fn is_secure(&self) -> bool {
        true
    }
}