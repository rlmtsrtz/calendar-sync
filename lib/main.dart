import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fussball.de Calendar Generator',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: const CalendarDashboard(),
    );
  }
}

class CalendarDashboard extends StatefulWidget {
  const CalendarDashboard({super.key});

  @override
  State<CalendarDashboard> createState() => _CalendarDashboardState();
}

class _CalendarDashboardState extends State<CalendarDashboard> {
  List<dynamic> _teams = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchTeams();
  }

  Future<void> _fetchTeams() async {
    try {
      // In a real deployed app, this would fetch from the same origin
      // For now, we simulate the structure
      final response = await http.get(Uri.parse('teams.json'));
      if (response.statusCode == 200) {
        setState(() {
          _teams = json.decode(response.body);
          _isLoading = false;
        });
      } else {
        // Fallback or error handling
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Fussball.de Kalender Abonnieren'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Verfügbare Mannschaften',
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: ListView.builder(
                      itemCount: _teams.length,
                      itemBuilder: (context, index) {
                        final team = _teams[index];
                        return Card(
                          child: ListTile(
                            title: Text(team['name']),
                            subtitle: Text('ID: ${team['id']}'),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.copy),
                                  tooltip: 'Webcal Link kopieren',
                                  onPressed: () {
                                    final baseUrl = Uri.base.toString().split('#')[0];
                                    final webcalUrl = 'webcal://${Uri.parse(baseUrl).host}${Uri.parse(baseUrl).path}calendars/${team['id']}.ics';
                                    // In real web app, use Clipboard.setData
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(content: Text('Link kopiert: $webcalUrl')),
                                    );
                                  },
                                ),
                                IconButton(
                                  icon: const Icon(Icons.download),
                                  tooltip: 'ICS herunterladen',
                                  onPressed: () {
                                    final baseUrl = Uri.base.toString().split('#')[0];
                                    final url = '${baseUrl}calendars/${team['id']}.ics';
                                    // Logic to trigger download
                                  },
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton.icon(
                    onPressed: () {
                      // Open GitHub Issues link to add team
                      // window.open('https://github.com/USER/REPO/issues/new?template=add_team.md', '_blank');
                    },
                    icon: const Icon(Icons.add),
                    label: const Text('Mannschaft hinzufügen (via GitHub Issue)'),
                  ),
                ],
              ),
            ),
    );
  }
}
