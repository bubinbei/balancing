# Переносимое ядро и граница аппаратной сборки

`core/` — C99 без SDK: CRC/сериализация BLC1, ограниченная очередь захватов и расширение TIMER timestamps с отказом при неопределённой паузе. Это проверяемая подготовка G01/G03/G04; готового образа NiceNano пока нет.

Native-проверка на Windows с установленным Visual Studio 2019 Build Tools:

```powershell
cmake -S firmware -B build/firmware-native -G "Visual Studio 16 2019" -A x64
cmake --build build/firmware-native --config Release
ctest --test-dir build/firmware-native -C Release --output-on-failure
```

На системе с другим компилятором выбрать её native generator; это не дополнительная аппаратная платформа. `test_core --vector` выводит hex кадра для сравнения с независимым `sample-negative` в тестах Python.

В очереди функции `*_locked` требуют внешней ISR-safe защиты на реальном MCU. Native-тесты проверяют порядок/переполнение, но не межпоточное исполнение и длительность критических секций. Сериализатор не валидирует регистровые данные вместо драйвера. Coarse-clock в timebase только обнаруживает неоднозначную паузу; его значение не подменяет аппаратный capture.

Для G01 ещё нужны паспорт клона, загрузчик, Flash layout, board target, точная версия SDK и проверка владения периферией. Без них нет pin overlay, linker script для этой платы, UF2 и команды прошивки. Build этого ядра не считается build_passed/device_passed полного G01. COM и аппаратные устройства native-проверка не использует.
