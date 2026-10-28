using System;
using System.Buffers.Binary;
using System.IO;
using System.Security.Cryptography;
using PKHeX.Core;

Console.OutputEncoding = System.Text.Encoding.UTF8;

try
{
    var options = Options.Parse(args);
    if (options.ShowHelp)
    {
        Options.PrintHelp();
        return 0;
    }
    if (options.SelfTest)
    {
        RunSelfTest();
        return 0;
    }

    var input = options.Input ?? PromptForInput();
    ConvertPk5(input, options.Output ?? Path.ChangeExtension(input, ".pgf"), options);
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"오류: {ex.Message}");
    return 1;
}

static void RunSelfTest()
{
    var folder = Path.Combine(Path.GetTempPath(), $"pk5-pgf-test-{Guid.NewGuid():N}");
    Directory.CreateDirectory(folder);
    try
    {
        var pk = new PK5
        {
            Species = 25,
            PID = 0x12345678,
            TID16 = 12345,
            SID16 = 54321,
            Language = 8,
            Version = GameVersion.B,
            Ball = 4,
            MetLevel = 25,
            CurrentLevel = 25,
            Nature = Nature.Jolly,
            Gender = 0,
            AbilityNumber = 1,
            OriginalTrainerName = "TEST",
            Nickname = "Pikachu",
            MetLocation = 30001,
            MetDate = new DateOnly(2026, 10, 6),
            Move1 = 85,
        };
        pk.SetIVs([31, 30, 29, 28, 27, 26]);
        pk.RefreshChecksum();
        var stored = new byte[136];
        pk.WriteEncryptedDataStored(stored);

        var input = Path.Combine(folder, "sample.pk5");
        var output = Path.Combine(folder, "sample.pgf");
        File.WriteAllBytes(input, stored);
        ConvertPk5(input, output, new Options());

        var gift = new PGF(File.ReadAllBytes(output));
        if (gift.Species != 25 || gift.TID16 != 12345 || gift.Move1 != 85 || gift.Data.Length != PGF.Size)
            throw new InvalidDataException("자체 테스트 결과의 필드가 일치하지 않습니다.");
        Console.WriteLine("자체 테스트 통과");
    }
    finally
    {
        Directory.Delete(folder, true);
    }
}

static string PromptForInput()
{
    Console.Write("PK5 파일 경로를 입력하거나 파일을 이 창에 끌어놓으세요: ");
    var value = Console.ReadLine()?.Trim().Trim('"');
    if (string.IsNullOrWhiteSpace(value))
        throw new ArgumentException("입력 파일이 지정되지 않았습니다.");
    return value;
}

static void ConvertPk5(string inputPath, string outputPath, Options options)
{
    inputPath = Path.GetFullPath(inputPath);
    outputPath = Path.GetFullPath(outputPath);
    if (!File.Exists(inputPath))
        throw new FileNotFoundException("PK5 파일을 찾을 수 없습니다.", inputPath);

    var raw = File.ReadAllBytes(inputPath);
    if (raw.Length is not (136 or 220))
        throw new InvalidDataException($"PK5 크기는 136 또는 220바이트여야 합니다. 현재: {raw.Length}바이트");

    var pk = new PK5(raw);
    if (pk.Species is 0 or > 649)
        throw new InvalidDataException($"유효한 5세대 포켓몬 종 번호가 아닙니다: {pk.Species}");
    if (!pk.ChecksumValid)
        throw new InvalidDataException("PK5 체크섬이 올바르지 않습니다. PKHeX에서 다시 내보내세요.");

    var title = options.Title ?? $"{pk.Nickname} 선물";
    var cardId = options.CardId ?? StableCardId(raw);
    var pgf = CreateGift(pk, title, cardId, options);

    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    File.WriteAllBytes(outputPath, pgf.Data.ToArray());

    var result = File.ReadAllBytes(outputPath);
    var verified = new PGF(result);
    if (result.Length != PGF.Size || !verified.IsEntity || verified.Species != pk.Species || verified.CardID != cardId)
        throw new InvalidDataException("생성된 PGF 자체 검증에 실패했습니다.");

    Console.WriteLine("변환 완료");
    Console.WriteLine($"입력 : {inputPath}");
    Console.WriteLine($"출력 : {outputPath}");
    Console.WriteLine($"포켓몬: {pk.Nickname} (종 번호 {pk.Species})");
    Console.WriteLine($"카드 ID: {cardId}");
    Console.WriteLine($"제목 : {title}");
    Console.WriteLine($"크기 : {result.Length}바이트");
}

static PGF CreateGift(PK5 pk, string title, ushort cardId, Options options)
{
    var pgf = new PGF
    {
        TID16 = pk.TID16,
        SID16 = pk.SID16,
        OriginGame = options.KeepOriginGame ? (byte)pk.Version : (byte)0,
        PID = pk.PID,
        Ball = pk.Ball,
        HeldItem = pk.HeldItem,
        Move1 = pk.Move1,
        Move2 = pk.Move2,
        Move3 = pk.Move3,
        Move4 = pk.Move4,
        Species = pk.Species,
        Form = pk.Form,
        Language = pk.Language,
        Nature = pk.Nature,
        Gender = pk.Gender,
        AbilityType = AbilityType(pk),
        PIDType = pk.IsShiny ? 2 : 1,
        EggLocation = pk.EggLocation,
        Location = pk.MetLocation,
        MetLevel = pk.MetLevel,
        ContestCool = pk.ContestCool,
        ContestBeauty = pk.ContestBeauty,
        ContestCute = pk.ContestCute,
        ContestSmart = pk.ContestSmart,
        ContestTough = pk.ContestTough,
        ContestSheen = pk.ContestSheen,
        OriginalTrainerName = pk.OriginalTrainerName,
        OTGender = pk.OriginalTrainerGender,
        IsEgg = pk.IsEgg,
        CardTitle = title,
        // WC5FULL downloads require the received-date field to be blank.
        // The game writes the actual redemption date when the card is received.
        Date = null,
        CardID = cardId,
        CardLocation = options.CardLocation,
        IsEntity = true,
        MultiObtain = options.MultiObtain,

        RibbonCountry = pk.RibbonCountry,
        RibbonNational = pk.RibbonNational,
        RibbonEarth = pk.RibbonEarth,
        RibbonWorld = pk.RibbonWorld,
        RibbonClassic = pk.RibbonClassic,
        RibbonPremier = pk.RibbonPremier,
        RibbonEvent = pk.RibbonEvent,
        RibbonBirthday = pk.RibbonBirthday,
        RibbonSpecial = pk.RibbonSpecial,
        RibbonSouvenir = pk.RibbonSouvenir,
        RibbonWishing = pk.RibbonWishing,
        RibbonChampionBattle = pk.RibbonChampionBattle,
        RibbonChampionRegional = pk.RibbonChampionRegional,
        RibbonChampionNational = pk.RibbonChampionNational,
        RibbonChampionWorld = pk.RibbonChampionWorld,
    };

    Span<int> ivs = stackalloc int[6];
    pk.GetIVs(ivs);
    pgf.IVs = ivs.ToArray();

    // PGF has no current EXP/EV storage. Deliver at the PK5's current level.
    pgf.Data[0x5B] = pk.CurrentLevel;
    // PGF requires an unnamed Pokemon's nickname field to be filled with
    // 0xFFFF words. Leaving the freshly allocated field as zeroes makes the
    // retail game's Wonder Card validator reject the download.
    pgf.Nickname = pk.IsNicknamed ? pk.Nickname : string.Empty;

    return pgf;
}

static int AbilityType(PK5 pk) => pk.AbilityNumber switch
{
    1 => 0,
    2 => 1,
    4 => 2,
    _ => throw new InvalidDataException($"지원하지 않는 특성 슬롯 값입니다: {pk.AbilityNumber}"),
};

static ushort StableCardId(ReadOnlySpan<byte> data)
{
    Span<byte> digest = stackalloc byte[32];
    SHA256.HashData(data, digest);
    var value = BinaryPrimitives.ReadUInt16LittleEndian(digest);
    return (ushort)((value % Options.MaxCardId) + 1);
}

sealed class Options
{
    public const ushort MaxCardId = 2047;

    public string? Input { get; private set; }
    public string? Output { get; private set; }
    public string? Title { get; private set; }
    public ushort? CardId { get; private set; }
    public byte CardLocation { get; private set; } = 68;
    public bool MultiObtain { get; private set; } = true;
    public bool KeepOriginGame { get; private set; }
    public bool ShowHelp { get; private set; }
    public bool SelfTest { get; private set; }

    public static Options Parse(string[] args)
    {
        var result = new Options();
        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            switch (arg.ToLowerInvariant())
            {
                case "-h" or "--help": result.ShowHelp = true; break;
                case "--self-test": result.SelfTest = true; break;
                case "-o" or "--output": result.Output = Next(args, ref i, arg); break;
                case "--title": result.Title = Next(args, ref i, arg); break;
                case "--card-id": result.CardId = ParseCardId(Next(args, ref i, arg)); break;
                case "--card-location": result.CardLocation = byte.Parse(Next(args, ref i, arg)); break;
                case "--multi-obtain": result.MultiObtain = true; break;
                case "--repeatable": result.MultiObtain = false; break;
                case "--keep-origin-game": result.KeepOriginGame = true; break;
                default:
                    if (arg.StartsWith('-')) throw new ArgumentException($"알 수 없는 옵션입니다: {arg}");
                    if (result.Input is not null) throw new ArgumentException("입력 PK5는 하나만 지정할 수 있습니다.");
                    result.Input = arg;
                    break;
            }
        }
        return result;
    }

    private static string Next(string[] args, ref int index, string option)
    {
        if (++index >= args.Length) throw new ArgumentException($"{option} 뒤에 값이 필요합니다.");
        return args[index];
    }

    private static ushort ParseCardId(string value)
    {
        if (!ushort.TryParse(value, out var result) || result is 0 or > MaxCardId)
            throw new ArgumentException($"5세대 카드 ID는 1~{MaxCardId}여야 합니다.");
        return result;
    }

    public static void PrintHelp()
    {
        Console.WriteLine("5세대 PK5 -> PGF 배포파일 변환기");
        Console.WriteLine("사용법: PK5를 PGF로 변환.cmd 또는 dotnet Gen5Converter.dll pokemon.pk5 [옵션]");
        Console.WriteLine("  -o, --output PATH       출력 PGF 경로");
        Console.WriteLine("  --title TEXT            원더카드 제목");
        Console.WriteLine("  --card-id 1-2047        카드 ID");
        Console.WriteLine("  --card-location 0-255   원더카드 출처 문구(기본 68)");
        Console.WriteLine("  --repeatable            반복형 특수 카드 상태 사용(고급)");
        Console.WriteLine("  --keep-origin-game      원본 버전만 수신 가능하게 제한");
        Console.WriteLine("  --self-test             내장 변환 테스트 실행");
    }
}
