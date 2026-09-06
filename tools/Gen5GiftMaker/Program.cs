using PKHeX.Core;

if (args.Length != 1)
{
    Console.Error.WriteLine("usage: Gen5GiftMaker <output.pgf>");
    return 2;
}

var gift = new PGF
{
    TID16 = 2026,
    SID16 = 820,
    PID = 0,
    Ball = 16,
    Species = 25,
    Form = 0,
    Language = (int)LanguageID.Korean,
    Nature = Nature.Hardy,
    Gender = 2,
    AbilityType = 3,
    PIDType = 1,
    Location = 30003,
    MetLevel = 50,
    OriginalTrainerName = "CODEX",
    OTGender = 0,
    CardTitle = "CODEX 테스트 피카츄",
    Date = new DateOnly(2026, 8, 20),
    CardID = 9001,
    CardLocation = 1,
    CardType = 1,
    MultiObtain = true,
};

gift.Data[0x5B] = 50;
gift.IVs = [255, 255, 255, 255, 255, 255];

var output = Path.GetFullPath(args[0]);
Directory.CreateDirectory(Path.GetDirectoryName(output)!);
File.WriteAllBytes(output, gift.Write().ToArray());

var parsed = new PGF(File.ReadAllBytes(output));
if (!parsed.IsEntity || parsed.Species != 25 || parsed.Level != 50 || parsed.CardID != 9001)
    throw new InvalidDataException("PKHeX.Core PGF round-trip validation failed.");

Console.WriteLine($"{output} ({new FileInfo(output).Length} bytes)");
Console.WriteLine($"Card={parsed.CardID}, Species={parsed.Species}, Level={parsed.Level}, Title={parsed.CardTitle}");
return 0;
