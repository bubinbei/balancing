---
status: not_ready_for_final_audit
updated: 2026-10-29
---

# Промежуточная поставка: программная часть

**Полный план не завершён.** Этот пакет сохраняет проверяемую подготовку, пока заказанные модули не получены и паспорт клона/ротора не подтверждён. Это не запрос окончательного аудита G14 и не аппаратная приёмка.

## Что существует

- [Host/CLI и воспроизведение](../../host/README.md): simulate, inspect, replay, record adapter, analyze, solve, size.
- [Переносимое C99-ядро](../../firmware/BUILD.md): wire encoding/CRC, очередь, timebase, словоформаты датчиков; native tests. Образа платы нет.
- [Паспорта](../../hardware/board-passport.md): подтверждён клон NiceNano; заказаны два BMI160, два LIS3DH и KY-033. Фактические GPIO/схема/загрузчик/ротор неизвестны.
- Независимые synthetic wire fixtures, математические проверки, fault injection, короткий host benchmark и frozen Python lock.

## Что проверять

| Заявление | Реализация | Проверка / доказательство |
|---|---|---|
| Фрейминг, CRC, CONFIG, sequence/epoch, raw/replay | host/balancing_host/protocol.py, session.py, recording.py | [G02](G02.md), tests/protocol, независимые fixtures |
| Контролируемые команды и конечные повторы | host/balancing_host/commands.py | tests/protocol/test_recording.py; MCU-сервер не проверен |
| Пакетная установка | pyproject.toml, uv.lock | [G14](G14.md), отдельная non-editable среда |
| C сериализация/clock/очередь | firmware/core | [G01](G01.md), [G04](G04.md), CTest, golden comparison |
| 1× / FFT / angular average и две плоскости | host/balancing_host/analysis.py | [G07](G07.md), 250 реализаций условной модели |
| θ/ω/α и модель roll/yaw | Phase.kinematics, rigid_body_acceleration | [G11](G11.md), timestamps 1 мкс, заданная ориентация |
| Bootstrap повторных прогонов | host/balancing_host/uncertainty.py | [G12](G12.md), synthetic calibration-noise test |
| Сбои записи и короткая скорость host | recording.py | [G13](G13.md), crash/disk-full/tail/hash tests |
| Расчётная подготовка подвеса | mechanics.py, mechanics/sizing-example.json | [G06](G06.md), пример с manufacturing_approval=false |

## Проверяемые команды

```powershell
uv sync --frozen
uv run python tools/check_project.py
uv run python -m unittest discover -s tests -v
cmake -S firmware -B build/firmware-native -G "Visual Studio 16 2019" -A x64
cmake --build build/firmware-native --config Release
ctest --test-dir build/firmware-native -C Release --output-on-failure
```

Проверялось на Windows / Python 3.12.6 / uv 0.12.13 / MSVC 19.29.30154. Другие toolchain/версии платы не объявлены принятыми. Исходники текущей поставки — HEAD; финальная ревизия сообщается после push, чтобы не вписывать рекурсивно SHA содержащего файла.

Заключительные результаты: 57/57 Python-тестов из non-editable среды; 1/1 CTest в Release; 12/12 исходников wheel совпали с текущим проектом, native C wire-vector совпал с независимым эталоном. Эти проверки не помечают карточки с аппаратными зависимостями как passed. Включены control-only USB emulator, отказ по деградированному END и сохранение признака незавершённой сессии при reset; реального порта/измерений в этих тестах нет.

## Реальные ограничения

Нет принятого G00, точного firmware target/linker map/UF2, SPI/DRDY/GPIOTE/USBD adapter, реального серверного кэша команд, свежести каналов, электрических измерений, геометрии/прочности/смазки/защиты и вращательных опытов. Не проведены длинные физические испытания, реальные пробные грузы и слепая проверка остатка. Неизвестен предел обнаружения. Цель 100 г·мм: not_tested.

CLI record добавлен как подготовка интеграции, реальный порт не открывался. Offline analyze пока требует один чистый завершённый epoch/UUID и выбранный источник; автоматического сегментирования повреждений и полного операторского калибровочного UI нет. Ковариация solve условна по заданной H; bootstrap добавляет разброс повторных прогонов, но не устраняет систематическую ошибку привода/геометрии. Ориентация для 3D synthetic-проверки задана, а не восстановлена IMU estimator.

## Данные и публикация

Все созданные измерительные файлы — synthetic/model_example. Локальные raw-архивы в data/runs исключены из Git; необходимые алгоритмические fixtures и численные отчёты публичны. Результаты G07 воспроизводятся инструментом tools/verify_synthetic.py с новым --output. Benchmark хранит сводку временного synthetic-архива; не заявляет доступность исходника измерения ротора.

Площадки: [GitHub](https://github.com/bubinbei/balancing), [Gitea](http://192.168.1.124:3000/bubinbei/balancing). Gitea использует локальный адрес. После последнего push сверяются HEAD/main обеих площадок и анонимная видимость. Независимый аудит не выполнялся.

Следующее внешнее событие: получение модулей и подтверждение паспорта/загрузчика/геометрии. После этого продолжить G00 → G01, интегрировать готовые программные компоненты и пройти фактические проверки остальных карточек.
