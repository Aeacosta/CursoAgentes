# Reporte
Código: ReportGenerator.cs

# Resumen
- **Long Parameter List** – El método `GenerateReport` recibe 12 parámetros primitivos, lo que dificulta su lectura, uso y mantenimiento (Martin, *Clean Code*, p. 107).  
- **Primitive Obsession** – Se usan tipos primitivos (`string`, `bool`, `DateTime`) para representar conceptos de dominio como correo electrónico, teléfono y opciones de reporte (Martin, *Clean Code*, p. 112).  
- **Data Clumps** – Los grupos `customerName/customerEmail/customerPhone`, `reportTitle/startDate/endDate/includeCharts/includeSummary/includeDetails` y `outputPath/author/company` aparecen juntos repetidamente, indicando que deberían estar encapsulados en objetos (Martin, *Clean Code*, p. 115).  
- **Side‑Effect Logging** – El método escribe directamente en la consola, mezclando responsabilidad de generación de reporte con salida de información (violación del Single Responsibility Principle).  

# Código con Problema
```csharp
public class ReportGenerator
{
    public void GenerateReport(
        string customerName,
        string customerEmail,
        string customerPhone,
        string reportTitle,
        DateTime startDate,
        DateTime endDate,
        bool includeCharts,
        bool includeSummary,
        bool includeDetails,
        string outputPath,
        string author,
        string company)
    {
        Console.WriteLine("Generating report...");
    }
}
```
**Violaciones presentes:**  
- 12 parámetros → *Long Parameter List*.  
- Uso de `string` para email y teléfono → *Primitive Obsession*.  
- Agrupaciones lógicas de parámetros sin abstracción → *Data Clumps*.  
- `Console.WriteLine` dentro del método → mezcla de responsabilidades (side‑effect).

# Código Arreglado
```csharp
using System;

namespace Reporting
{
    // Value objects que reemplazan los tipos primitivos
    public sealed class Email
    {
        public string Value { get; }
        public Email(string value) => Value = value ?? throw new ArgumentNullException(nameof(value));
    }

    public sealed class Phone
    {
        public string Value { get; }
        public Phone(string value) => Value = value ?? throw new ArgumentNullException(nameof(value));
    }

    // Agrupación de datos relacionados
    public class CustomerInfo
    {
        public string Name { get; }
        public Email Email { get; }
        public Phone Phone { get; }

        public CustomerInfo(string name, Email email, Phone phone)
        {
            Name = name ?? throw new ArgumentNullException(nameof(name));
            Email = email ?? throw new ArgumentNullException(nameof(email));
            Phone = phone ?? throw new ArgumentNullException(nameof(phone));
        }
    }

    public class ReportOptions
    {
        public string Title { get; }
        public DateTime StartDate { get; }
        public DateTime EndDate { get; }
        public bool IncludeCharts { get; }
        public bool IncludeSummary { get; }
        public bool IncludeDetails { get; }

        public ReportOptions(string title, DateTime startDate, DateTime endDate,
                             bool includeCharts, bool includeSummary, bool includeDetails)
        {
            Title = title ?? throw new ArgumentNullException(nameof(title));
            StartDate = startDate;
            EndDate = endDate;
            IncludeCharts = includeCharts;
            IncludeSummary = includeSummary;
            IncludeDetails = includeDetails;
        }
    }

    public class ReportMetadata
    {
        public string OutputPath { get; }
        public string Author { get; }
        public string Company { get; }

        public ReportMetadata(string outputPath, string author, string company)
        {
            OutputPath = outputPath ?? throw new ArgumentNullException(nameof(outputPath));
            Author = author ?? throw new ArgumentNullException(nameof(author));
            Company = company ?? throw new ArgumentNullException(nameof(company));
        }
    }

    // Facade que oculta la complejidad de la creación del reporte
    public class ReportGenerator
    {
        private readonly IReportWriter _writer; // inyección de dependencia para pruebas

        public ReportGenerator(IReportWriter writer) => _writer = writer ?? throw new ArgumentNullException(nameof(writer));

        public void GenerateReport(CustomerInfo customer,
                                   ReportOptions options,
                                   ReportMetadata metadata)
        {
            // Aquí iría la lógica real de generación; se delega la salida al writer.
            _writer.WriteHeader(customer, options, metadata);
            _writer.WriteBody(options);
            _writer.WriteFooter();
        }
    }

    // Interfaz que permite cambiar el destino de la salida (consola, archivo, etc.)
    public interface IReportWriter
    {
        void WriteHeader(CustomerInfo customer, ReportOptions options, ReportMetadata metadata);
        void WriteBody(ReportOptions options);
        void WriteFooter();
    }

    // Implementación concreta que escribe en consola (puede reemplazarse por un logger o archivo)
    public class ConsoleReportWriter : IReportWriter
    {
        public void WriteHeader(CustomerInfo customer, ReportOptions options, ReportMetadata metadata)
        {
            Console.WriteLine($"Reporte: {options.Title}");
            Console.WriteLine($"Cliente: {customer.Name} <{customer.Email.Value}>");
            Console.WriteLine($"Periodo: {options.StartDate:d} - {options.EndDate:d}");
            Console.WriteLine($"Generado por: {metadata.Author} ({metadata.Company})");
            Console.WriteLine();
        }

        public void WriteBody(ReportOptions options)
        {
            Console.WriteLine("Opciones de reporte:");
            Console.WriteLine($"  Incluir gráficos: {options.IncludeCharts}");
            Console.WriteLine($"  Incluir resumen:  {options.IncludeSummary}");
            Console.WriteLine($"  Incluir detalles: {options.IncludeDetails}");
            Console.WriteLine();
        }

        public void WriteFooter()
        {
            Console.WriteLine("--- Fin del reporte ---");
        }
    }
}
```

**Mejoras aplicadas:**  
- Se redujo la lista de parámetros a tres objetos cohesivos (`CustomerInfo`, `ReportOptions`, `ReportMetadata`).  
- Se eliminó la *Primitive Obsession* introdu