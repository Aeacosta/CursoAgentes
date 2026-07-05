To implement proper unit testing in Python using pytest, your tests should follow the Arrange-Act-Assert (AAA) pattern, use descriptive naming conventions, and leverage modular fixtures for setup and teardown

1. Basic AAA Structure and Descriptive Naming
A well-structured test clearly separates setup from execution and verification, using a name that explains the scenario, condition, and expected outcome

# File: test_models.py
from my_app.models import Note, categorize_by_count

```python
def test_categorize_by_count_high_word_count_returns_long():
    # Arrange: Set up the data and objects the test needs
    word_count = 500
    
    # Act: Call the specific function being tested
    result = categorize_by_count(word_count)
    
    # Assert: Inspect the output against expected invariants
    assert result == "long"
```    
Separating these phases provides immediate diagnostic clarity; if a failure occurs in the Arrange phase, the framework signals a setup error rather than a failure of business logic

2. Using Fixtures for Modular Setup
Fixtures provide a consistent context for tests, handling repetitive setup logic like creating complex objects or database connections
 By requesting a fixture as a parameter, you implement a dependency injection pattern

```python
import pytest
from my_app.models import Note

@pytest.fixture
def sample_note():
    """Provides a fresh Note object for each test."""
    return Note(title="Ideas", body="This is a test body.")

def test_note_stores_body_correctly(sample_note):
    # Arrange: Done automatically by the fixture
    expected_body = "This is a test body."
    
    # Act: Trigger the state-changing action
    actual_body = sample_note.body
    
    # Assert: Verify the result
    assert actual_body == expected_body
```

This ensures test isolation, as each function receives its own "fresh" batch of data from the fixture

3. Parametrization for Edge Cases
To avoid code duplication when testing multiple scenarios, use @pytest.mark.parametrize
This allows you to run the same test logic with different inputs and expected outputs

```python
import pytest
from my_app.utils import calculate_tax

@pytest.mark.parametrize("price, rate, expected", [
    (100, 0.1, 10),
    (200, 0.05, 10),
    (0, 0.1, 0),
])
def test_calculate_tax_various_inputs_return_correct_amount(price, rate, expected):
    # Act
    result = calculate_tax(price, rate)
    
    # Assert
    assert result == expected
```

This practice improves coverage for edge cases while keeping the test suite concise and maintainable

4. Mocking External Dependencies
Unit tests must run in isolation from external services like databases or APIs
 Use mocker.patch to replace real implementations with mock objects that return pre-set values

```python
def test_get_user_email_from_api_success(mocker):
    # Arrange: Mock the external API response
    mock_response = mocker.patch("my_app.api_client.fetch_user")
    mock_response.return_value = {"email": "test@example.com"}
    
    # Act
    from my_app.services import get_user_email
    email = get_user_email(user_id=1)
    
    # Assert
    assert email == "test@example.com"
```    
By mocking, you ensure tests are fast and deterministic, avoiding failures caused by network instability or database state

5. Yield Fixtures for Resource Cleanup
For resources that must be cleaned up (like temporary files or connections), use yield fixtures
 Pytest executes the code after the yield statement once the test is finished, even if it fails

```python
@pytest.fixture
def temp_database_connection():
    # Arrange: Setup resource
    conn = create_db_connection()
    yield conn  # Provide the resource to the test
    
    # Cleanup: Teardown logic
    conn.close()
```    
This prevents cross-test pollution and ensures that the test environment is restored to its baseline state
