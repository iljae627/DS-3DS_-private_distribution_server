using System.Buffers.Binary;
using System.Security.Cryptography;
using PKHeX.Core;

Console.OutputEncoding = System.Text.Encoding.UTF8;
try
{
    var options = Options.Parse(args);
    if (options.ShowHelp) { Options.PrintHelp(); return 0; }
    var input = options.Input ?? PromptForInput();
    ConvertPk4(input, options.Output ?? Path.ChangeExtension(input, ".pcd"), options);
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"오류: {ex.Message}");
    return 1;
}

static string PromptForInput()
{
    Console.Write("PK4 파일 경로를 입력하거나 파일을 이 창에 끌어놓으세요: ");
    var value = Console.ReadLine()?.Trim().Trim('"');
    if (string.IsNullOrWhiteSpace(value)) throw new ArgumentException("입력 파일이 지정되지 않았습니다.");
    return value;
}

static void ConvertPk4(string inputPath, string outputPath, Options options)
{
    inputPath = Path.GetFullPath(inputPath);
    outputPath = Path.GetFullPath(outputPath);
    if (!File.Exists(inputPath)) throw new FileNotFoundException("PK4 파일을 찾을 수 없습니다.", inputPath);
    var raw = File.ReadAllBytes(inputPath);
    if (raw.Length is not (136 or 236))
        throw new InvalidDataException($"PK4 크기는 136 또는 236바이트여야 합니다. 현재: {raw.Length}바이트");

    var pk = new PK4(raw);
    if (pk.Species is 0 or > 493) throw new InvalidDataException($"유효한 4세대 포켓몬 종 번호가 아닙니다: {pk.Species}");
    if (!pk.ChecksumValid) throw new InvalidDataException("PK4 체크섬이 올바르지 않습니다. PKHeX에서 다시 내보내세요.");

    var title = options.Title ?? $"A special {pk.Nickname}!";
    var description = options.Description ?? "Please accept this special Pokemon gift!";
    var cardId = options.CardId ?? StableCardId(raw);
    var pcd = new PCD();
    pcd.Gift.GiftType = pk.IsEgg ? GiftType4.PokémonEgg : GiftType4.Pokémon;
    pcd.Gift.Slot = 0;
    pcd.Gift.Detail = 0;
    pcd.Gift.ItemID = options.GiftInstance;
    pcd.Gift.PK = pk;
    pcd.CardTitle = title;
    pcd.CardID = cardId;

    var data = pcd.Data;
    BinaryPrimitives.WriteUInt16BigEndian(data[0x14C..0x14E], options.GameMask);
    StringConverter4.SetString(data.Slice(0x154, 0x1F4), description, 250, 0, StringConverterOption.ClearFF);
    data[0x348] = options.Redistribution;
    BinaryPrimitives.WriteUInt16LittleEndian(data[0x34A..0x34C], 0);
    BinaryPrimitives.WriteUInt16LittleEndian(data[0x34C..0x34E], pk.Species);
    BinaryPrimitives.WriteUInt16LittleEndian(data[0x34E..0x350], 0);

    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    File.WriteAllBytes(outputPath, pcd.Write().ToArray());
    var verified = new PCD(File.ReadAllBytes(outputPath));
    if (verified.Data.Length != PCD.Size || verified.Gift.Species != pk.Species)
        throw new InvalidDataException("생성된 PCD 자체 검증에 실패했습니다.");

    Console.WriteLine("변환 완료");
    Console.WriteLine($"입력 : {inputPath}");
    Console.WriteLine($"출력 : {outputPath}");
    Console.WriteLine($"포켓몬: {pk.Nickname} (종 번호 {pk.Species})");
    Console.WriteLine($"카드 ID: {cardId}");
    Console.WriteLine($"제목 : {title}");
    Console.WriteLine($"크기 : {new FileInfo(outputPath).Length}바이트");
}

static ushort StableCardId(ReadOnlySpan<byte> data)
{
    Span<byte> digest = stackalloc byte[32];
    SHA256.HashData(data, digest);
    var value = BinaryPrimitives.ReadUInt16LittleEndian(digest);
    return value == 0 ? (ushort)1 : value;
}

sealed class Options
{
    public string? Input { get; private set; }
    public string? Output { get; private set; }
    public string? Title { get; private set; }
    public string? Description { get; private set; }
    public ushort? CardId { get; private set; }
    public int GiftInstance { get; private set; } = 1;
    public ushort GameMask { get; private set; } = 0x801D;
    public byte Redistribution { get; private set; }
    public bool ShowHelp { get; private set; }

    public static Options Parse(string[] args)
    {
        var result = new Options();
        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            switch (arg.ToLowerInvariant())
            {
                case "-h" or "--help": result.ShowHelp = true; break;
                case "-o" or "--output": result.Output = Next(args, ref i, arg); break;
                case "--title": result.Title = Next(args, ref i, arg); break;
                case "--description": result.Description = Next(args, ref i, arg); break;
                case "--card-id": result.CardId = ushort.Parse(Next(args, ref i, arg)); break;
                case "--gift-instance": result.GiftInstance = int.Parse(Next(args, ref i, arg)); break;
                case "--games": result.GameMask = ParseGames(Next(args, ref i, arg)); break;
                case "--redistribution": result.Redistribution = byte.Parse(Next(args, ref i, arg)); break;
                default:
                    if (arg.StartsWith('-')) throw new ArgumentException($"알 수 없는 옵션입니다: {arg}");
                    if (result.Input is not null) throw new ArgumentException("입력 PK4는 하나만 지정할 수 있습니다.");
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

    private static ushort ParseGames(string value)
    {
        ushort mask = 0;
        foreach (var game in value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            mask |= game.ToLowerInvariant() switch
            {
                "diamond" or "d" => 1 << 2, "pearl" or "p" => 1 << 3,
                "platinum" or "pt" => 1 << 4, "heartgold" or "hg" => 1 << 15,
                "soulsilver" or "ss" => 1 << 0, "all" => 0x801D,
                _ => throw new ArgumentException($"알 수 없는 게임입니다: {game}"),
            };
        if (mask == 0) throw new ArgumentException("호환 게임을 하나 이상 지정해야 합니다.");
        return mask;
    }

    public static void PrintHelp()
    {
        Console.WriteLine("4세대 PK4 -> PCD 배포파일 변환기");
        Console.WriteLine("사용법: 배포파일 변환기.exe pokemon.pk4 [옵션]");
        Console.WriteLine("  -o, --output PATH       출력 PCD 경로");
        Console.WriteLine("  --title TEXT            원더카드 제목");
        Console.WriteLine("  --description TEXT      원더카드 설명");
        Console.WriteLine("  --card-id 1-65535       카드 ID");
        Console.WriteLine("  --games all|d,p,pt,hg,ss  호환 게임");
        Console.WriteLine("  --redistribution 0-255  재배포 횟수(255=무제한)");
    }
}
