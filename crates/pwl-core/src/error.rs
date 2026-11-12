use std::fmt;

#[derive(Debug)]
pub enum Error {
    /// Ввод пользователя не прошёл проверку. Текст уже готов к показу в UI.
    Validation(String),
    NotFound(&'static str),
    Io(std::io::Error),
    Codec(String),
    /// Файл данных повреждён; путь и причина.
    Corrupt(String),
    /// Клиент не найден — UI открывает модалку выбора пути.
    ClientMissing(String),
}

pub type Result<T> = std::result::Result<T, Error>;

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Validation(m) => write!(f, "{m}"),
            Error::NotFound(what) => write!(f, "{what} не найден"),
            Error::Io(e) => write!(f, "Ошибка диска: {e}"),
            Error::Codec(m) => write!(f, "Ошибка формата: {m}"),
            Error::Corrupt(m) => write!(f, "Файл данных повреждён: {m}"),
            Error::ClientMissing(m) => write!(f, "{m}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Error::Io(e)
    }
}

impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Error::Codec(e.to_string())
    }
}

impl Error {
    /// Код для UI: позволяет отличить «покажи модалку выбора клиента»
    /// от «просто покажи тост».
    pub fn code(&self) -> &'static str {
        match self {
            Error::Validation(_) => "validation",
            Error::NotFound(_) => "notFound",
            Error::Io(_) => "io",
            Error::Codec(_) => "codec",
            Error::Corrupt(_) => "corrupt",
            Error::ClientMissing(_) => "clientMissing",
        }
    }
}