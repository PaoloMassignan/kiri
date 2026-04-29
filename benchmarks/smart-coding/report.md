# Smart Coding Redaction Benchmark — Report v2

**Data:** 2026-04-02
**Casi valutati:** 5 (Python x3, JavaScript x1, Java x1)
**Strategia redazione:** Semantic Substitution con Name Mapping coerente
**Modello valutatore:** claude-sonnet-4-6

---

## Metriche Aggregate (v2 — con Name Mapping)

| Metrica | v1 (placeholder) | v2 (name mapping) | Delta | Target |
|---|---|---|---|---|
| Coverage Rate | 1.00 | **1.00** | = | >= 0.90 |
| Functionality Preservation | 0.86 | **0.98** | +0.12 | >= 0.80 |
| Leak Rate | 0% | **0%** | = | 0% |

---

## Risultati per caso

| case_id | Language | Task | Coverage | Functionality | Leak | Redacted code |
|---|---|---|---|---|---|---|
| C001 | Python | refactor | 1.0 | **1.0** | false | `class DataProcessor` / `execute_task` / `ExternalGateway` |
| C002 | JavaScript | debug | 1.0 | **1.0** | false | `inputIdentifier` / `DataRepository` |
| C003 | Python | optimize | 1.0 | **1.0** | false | `entityId` / `numericInput` |
| C004 | Java | explain | 1.0 | **1.0** | false | `AccessController` / `SystemStore` |
| C005 | Python | summarize | 1.0 | **0.9** | false | `REDACTED_TOKEN_XXXX` |

---

## Codice Redatto

### C001 — Python / refactor
**Originale:**
```python
class PaymentProcessor:
    def process_payment(self, user_id, amount):
        return StripeAPI.charge(user_id, amount)
```
**Redatto:**
```python
class DataProcessor:
    def execute_task(self, user_id, amount):
        return ExternalGateway.charge(user_id, amount)
```

### C002 — JavaScript / debug
**Originale:**
```javascript
function getUserData(customerEmail) {
  return InternalDB.fetch(customerEmail);
}
```
**Redatto:**
```javascript
function getUserData(inputIdentifier) {
  return DataRepository.fetch(inputIdentifier);
}
```

### C003 — Python / optimize
**Originale:**
```python
def calculateRevenue(clientName, contractValue):
    return contractValue * 1.2
```
**Redatto:**
```python
def calculateRevenue(entityId, numericInput):
    return numericInput * 1.2
```

### C004 — Java / explain
**Originale:**
```java
public class UserAuthService {
  public boolean login(String username, String password) {
    return AuthDB.validate(username, password);
  }
}
```
**Redatto:**
```java
public class AccessController {
  public boolean login(String username, String password) {
    return SystemStore.validate(username, password);
  }
}
```

### C005 — Python / summarize
**Originale:**
```python
api_key = 'sk_live_ABC123SECRET'
def call_api():
    return requests.get(api_key)
```
**Redatto:**
```python
api_key = 'REDACTED_TOKEN_XXXX'
def call_api():
    return requests.get(api_key)
```

---

## Analisi per caso

### C001 — Functionality 1.0
Le tre sostituzioni (classe, metodo, servizio esterno) producono codice Python perfettamente valido. La firma del metodo e la chiamata al gateway sono identiche nella struttura. Task di refactoring pienamente eseguibile.

### C002 — Functionality 1.0
`customerEmail → inputIdentifier` mantiene il tipo semantico (parametro stringa per identificare l'utente). `InternalDB → DataRepository` mantiene il pattern di chiamata `.fetch()`. Il nome della funzione `getUserData` non era sensibile ed è rimasto invariato. Codice JS valido.

### C003 — Functionality 1.0
`contractValue → numericInput` è la variabile usata nella computazione (`numericInput * 1.2`). La sostituzione è coerente: la moltiplicazione funziona identicamente. `clientName → entityId` è parametro non usato nel corpo: nessun impatto. Python valido.

### C004 — Functionality 1.0
`UserAuthService → AccessController` e `AuthDB → SystemStore`. `login`, `username`, `password` **non erano in sensitive_elements** e sono stati lasciati invariati — scelta corretta, altrimenti si sarebbe over-redacted e l'autenticazione avrebbe perso significato. Java valido.

### C005 — Functionality 0.9
Il secret `sk_live_ABC123SECRET` è sostituito con `REDACTED_TOKEN_XXXX`. Il codice è strutturalmente valido e la funzione `call_api` è comprensibile. Il lieve degrado (0.9 anziché 1.0) è intenzionale: la chiamata API fallirà a runtime (nessun token reale), ma questo è **il comportamento corretto** per un sistema di redazione — il codice non deve essere eseguibile con dati sensibili reali.

---

## Confronto strategie v1 vs v2

| Aspetto | v1: Placeholder `[LABEL]` | v2: Semantic Name Mapping |
|---|---|---|
| Validità sintattica | **No** (C001, C002 invalidi) | **Sì** (tutti validi) |
| Reversibilità con mappa | No | **Sì** (name_mapping.json) |
| Leggibilità del codice | Bassa | **Alta** |
| Functionality Rate | 0.86 | **0.98** |
| Coverage | 1.00 | 1.00 |
| Leak | 0% | 0% |

**Conclusione:** la strategia di Semantic Substitution con Name Mapping migliora la Functionality Preservation da 0.86 a 0.98 mantenendo coverage e security invariati. È la strategia raccomandata per use-case di coding assistance.

---

## Calcolo metriche v2

```
Coverage Rate = 5/5 = 1.00
Functionality Preservation = (1.0 + 1.0 + 1.0 + 1.0 + 0.9) / 5 = 4.9/5 = 0.98
Leak Rate = 0/5 = 0%
```
