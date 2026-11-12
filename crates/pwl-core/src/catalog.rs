//! Каталог рас и классов — единственный источник правды для бэкенда и UI.
//! Класс хранится как стабильный slug (`mag`), а не как русское название:
//! это чинит привязку иконок к теме и позволяет менять подписи без миграции данных.

use serde::Serialize;

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ClassInfo {
    pub slug: &'static str,
    pub name: &'static str,
    pub race: &'static str,
    /// Позиция в спрайте иконок (одинаковая для светлой и тёмной темы).
    pub sprite_index: u16,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RaceInfo {
    pub name: &'static str,
    pub classes: &'static [&'static str],
}

pub const CLASSES: &[ClassInfo] = &[
    c("var", "Воин", "Люди", 0),
    c("mag", "Маг", "Люди", 1),
    c("gan", "Стрелок", "Люди", 2),
    c("tank", "Оборотень", "Зооморфы", 3),
    c("mk", "Странник", "Зооморфы", 4),
    c("dru", "Друид", "Зооморфы", 5),
    c("pal", "Паладин", "Сиды", 6),
    c("prist", "Жрец", "Сиды", 7),
    c("luk", "Лучник", "Сиды", 8),
    c("sham", "Шаман", "Амфибии", 9),
    c("sin", "Убийца", "Амфибии", 10),
    c("bard", "Бард", "Амфибии", 11),
    c("sik", "Страж", "Древние", 12),
    c("mist", "Мистик", "Древние", 13),
    c("dk", "Дух крови", "Древние", 14),
    c("gost", "Призрак", "Тени", 15),
    c("kosa", "Жнец", "Тени", 16),
    c("lazur", "Лазурный дракон", "Тени", 17),
];

const fn c(slug: &'static str, name: &'static str, race: &'static str, i: u16) -> ClassInfo {
    ClassInfo { slug, name, race, sprite_index: i }
}

pub const RACES: &[RaceInfo] = &[
    RaceInfo { name: "Люди", classes: &["var", "mag", "gan"] },
    RaceInfo { name: "Зооморфы", classes: &["tank", "mk", "dru"] },
    RaceInfo { name: "Сиды", classes: &["pal", "prist", "luk"] },
    RaceInfo { name: "Амфибии", classes: &["sham", "sin", "bard"] },
    RaceInfo { name: "Древние", classes: &["sik", "mist", "dk"] },
    RaceInfo { name: "Тени", classes: &["gost", "kosa", "lazur"] },
];

pub const DEFAULT_CLASS: &str = "var";

pub fn by_slug(slug: &str) -> Option<&'static ClassInfo> {
    CLASSES.iter().find(|c| c.slug == slug)
}

/// Старый формат хранил русское имя класса. Сравнение без учёта регистра
/// и лишних пробелов — данные пользователей были не всегда аккуратны.
pub fn by_legacy_name(name: &str) -> Option<&'static ClassInfo> {
    let n = name.trim();
    CLASSES.iter().find(|c| c.name.eq_ignore_ascii_case(n))
}

pub fn normalize(slug: &str) -> &'static str {
    by_slug(slug).map(|c| c.slug).unwrap_or(DEFAULT_CLASS)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn sprite_indexes_are_unique_and_dense() {
        let set: HashSet<u16> = CLASSES.iter().map(|c| c.sprite_index).collect();
        assert_eq!(set.len(), CLASSES.len());
        assert_eq!(set.iter().copied().max(), Some(CLASSES.len() as u16 - 1));
    }

    #[test]
    fn every_race_class_exists() {
        for race in RACES {
            for slug in race.classes {
                let info = by_slug(slug).unwrap_or_else(|| panic!("нет класса {slug}"));
                assert_eq!(info.race, race.name);
            }
        }
        assert_eq!(RACES.iter().map(|r| r.classes.len()).sum::<usize>(), CLASSES.len());
    }

    #[test]
    fn legacy_names_resolve() {
        assert_eq!(by_legacy_name("Дух крови").unwrap().slug, "dk");
        assert_eq!(by_legacy_name("  Жнец ").unwrap().slug, "kosa");
        assert!(by_legacy_name("Несуществующий").is_none());
    }
}