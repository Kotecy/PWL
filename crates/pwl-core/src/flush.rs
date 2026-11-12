//! Политика отложенной записи. Чистая логика с внешними «часами», поэтому
//! тестируется без потоков и слипов.
//!
//! Идея: пачка правок (перетаскивание, ввод в форму, импорт) должна давать
//! одну запись на диск, а не N. Ждём `quiet` мс тишины, но не дольше `max` мс
//! от первой правки — чтобы при непрерывной работе данные всё равно сохранялись.

#[derive(Debug, Clone, Copy)]
pub struct Debouncer {
    quiet_ms: u64,
    max_ms: u64,
    first_dirty: Option<u64>,
    last_edit: u64,
}

impl Debouncer {
    pub fn new(quiet_ms: u64, max_ms: u64) -> Self {
        Self { quiet_ms, max_ms: max_ms.max(quiet_ms), first_dirty: None, last_edit: 0 }
    }

    pub fn edit(&mut self, now_ms: u64) {
        if self.first_dirty.is_none() {
            self.first_dirty = Some(now_ms);
        }
        self.last_edit = now_ms;
    }

    pub fn is_pending(&self) -> bool {
        self.first_dirty.is_some()
    }

    /// Момент, когда пора писать. `None` — писать нечего.
    pub fn deadline(&self) -> Option<u64> {
        self.first_dirty
            .map(|first| (self.last_edit + self.quiet_ms).min(first + self.max_ms))
    }

    pub fn due(&self, now_ms: u64) -> bool {
        self.deadline().map(|d| now_ms >= d).unwrap_or(false)
    }

    /// Сколько ждать до записи (для `recv_timeout`).
    pub fn wait_ms(&self, now_ms: u64) -> Option<u64> {
        self.deadline().map(|d| d.saturating_sub(now_ms))
    }

    pub fn clear(&mut self) {
        self.first_dirty = None;
        self.last_edit = 0;
    }
}

impl Default for Debouncer {
    fn default() -> Self {
        Self::new(150, 1_000)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn idle_never_flushes() {
        let d = Debouncer::default();
        assert!(!d.is_pending());
        assert!(!d.due(1_000_000));
        assert_eq!(d.wait_ms(0), None);
    }

    #[test]
    fn burst_of_edits_produces_single_flush() {
        let mut d = Debouncer::new(150, 1000);
        // 30 правок за 300 мс — ни одна не должна уйти на диск отдельно.
        for t in (0..300).step_by(10) {
            d.edit(t);
            assert!(!d.due(t), "рано писать на t={t}");
        }
        assert!(!d.due(439));
        assert!(d.due(440), "тишина 150 мс после последней правки (t=290)");
        d.clear();
        assert!(!d.is_pending());
    }

    #[test]
    fn max_delay_caps_continuous_editing() {
        let mut d = Debouncer::new(150, 1000);
        for t in (0..2000).step_by(50) {
            d.edit(t);
            if t >= 1000 {
                assert!(d.due(t), "не дольше max_ms от первой правки");
                break;
            }
        }
    }

    #[test]
    fn wait_ms_counts_down() {
        let mut d = Debouncer::new(100, 500);
        d.edit(1000);
        assert_eq!(d.wait_ms(1000), Some(100));
        assert_eq!(d.wait_ms(1050), Some(50));
        assert_eq!(d.wait_ms(1200), Some(0));
    }

    #[test]
    fn max_is_never_below_quiet() {
        let d = Debouncer::new(200, 10);
        assert_eq!(d.max_ms, 200);
    }
}