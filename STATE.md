---
updated: 2026-10-29
status: hardware_inputs_required
current_task: G00
---

# Текущее состояние

После P00 по прямому запросу владельца автоматически подготовлены доступные программные срезы. Host: BLC1/CRC, CONFIG/session/epoch, raw/events/metadata, replay с arrival timing, ограниченные команды, PySerial adapter, 1×/FFT/angular average, две плоскости, bootstrap. C99 core: кодек, очередь, timebase, LE16/HR12; native Release/CTest.

Владелец подтвердил: NiceNano — недорогой клон; заказаны два BMI160, два LIS3DH и KY-033. Ревизия/схема, INFO_UF2.TXT/Flash layout, фактические GPIO, питание и геометрия ротора неизвестны. G00/G01 blocked; G06 blocked на размерах/нагрузках. G02/G04/G07/G11/G12/G13/G14 in_progress: подготовка и synthetic-проверки, без полной приёмки зависимостей. G03/G05/G08/G09/G10 planned.

Проверены 56 Python-тестов и 1 CTest; независимые wire-векторы, негативные входы, crash/disk-full/hash, аналитическая коррекция, jitter/clock drift/оси и неопределённость. Покрытие условной 95% области — 0,96 на 250 synthetic реализациях. Короткий host benchmark около 2,5–2,7 МБ/с, не тест USB. Полный список команд/ограничений: evidence/reports/AUDIT_PACKAGE.md. Зависимости зафиксированы uv.lock; выполнена отдельная non-editable установка и тесты.

Плата, COM и привод не использовались. Образа NiceNano/SPI-IRQ-USB adapter нет; физические 90 минут, смазка/защита, реальные грузы и остаток не проверены. 100 г·мм: not_tested. Финальный аудит не готов.

Следующее внешнее действие — получить детали и паспорт клона/загрузчика/ротора; затем закрыть G00 → G01 и продолжить аппаратные проверки автоматически. Программный demo: uv sync --frozen; см. host/README.md. Публичные GitHub/Gitea содержат проверяемые исходники; raw/build локальны.
