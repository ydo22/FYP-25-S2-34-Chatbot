<?php
require_once dirname(__DIR__, 2) . '/Controllers/Admin/AdminEditProductCtrl.php';

$controller = new AdminEditProductCtrl();
$error = '';
$successMsg = '';
if (isset($_GET['success']) && $_GET['success'] == '1') {
    $successMsg = 'Product edited successfully!';
}

// Fetch current product details if `id` is given
$product = null;
if (isset($_GET['id']) && !empty($_GET['id'])) {
    $product = $controller->getProductById($_GET['id']);
    if (!$product) {
        $error = "Product not found.";
    }
}

// Handle success message
if (isset($_GET['success']) && $_GET['success'] == '1') {
    $successMsg = 'Product edited successfully!';
}

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name = trim($_POST['name'] ?? '');
    $price = floatval($_POST['price'] ?? 0);
    $quantity = intval($_POST['quantity'] ?? 0);
    $description = trim($_POST['description'] ?? '');
    $category = trim($_POST['category'] ?? '');
    // Validate inputs
    if (empty($error)) {
        if (empty($name) || $price <= 0 || $quantity < 0 || empty($category)) {
            $error = "Please fill all required fields correctly.";
        }
    }
    
    // edit product if no errors
    if (empty($error)) {
        try {
            $id = intval($_POST['furnitureID'] ?? 0);
                $success = $controller->editProduct($id, $name, $category, $price, $quantity, $description);

            
            if ($success) {
                header("Location: AdminEditProduct.php?success=1");
                exit();
            } else {
                $error = "Failed to edit product. Please try again.";
            }
        } catch (mysqli_sql_exception $e) {
            $error = "Database error: " . $e->getMessage();
        } catch (Exception $e) {
            $error = "Error: " . $e->getMessage();
        }
    }
}
include '../../header.php';
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Add New Product</title>
    <link rel="stylesheet" href="../../style.css">
    <style>
        .form-container {
            max-width: 700px;
            margin: 100px auto 30px;
            padding: 30px;
            background: rgba(255,255,255,0.9);
            border-radius: 20px;
            box-shadow: 0 0 30px rgba(0,0,0,0.2);
        }
        
        .form-title {
            color: #e67e22;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2em;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        
        .form-group input[type="text"],
        .form-group input[type="number"],
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 6px;
            font-size: 1em;
        }
        
        .form-group textarea {
            height: 120px;
            resize: vertical;
        }
        
        .btn-submit {
            background-color: #2ecc71;
            color: white;
            padding: 12px 0;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1.1em;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s ease;
        }
        
        .btn-submit:hover {
            background-color: #27ae60;
        }
        
        .btn-cancel {
            display: block;
            text-align: center;
            margin-top: 15px;
            padding: 12px 0;
            background-color: #e74c3c;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
        }
        
        .error-message {
            color: #e74c3c;
            margin-bottom: 20px;
            padding: 15px;
            background: #ffebee;
            border-radius: 6px;
            border-left: 4px solid #e74c3c;
        }
    </style>
</head>
<body>
    <div class="form-container">
        <h2 class="form-title">Edit Product</h2>
        
        <?php if (!empty($successMsg)): ?>
            <div class="success-message"><?php echo htmlspecialchars($successMsg); ?></div>
        <?php endif; ?>

        <?php if (!empty($error)): ?>
            <div class="error-message"><?php echo htmlspecialchars($error); ?></div>
        <?php endif; ?>
                 
        <form method="POST" action="AdminEditProduct.php" enctype="multipart/form-data">
            <input type="hidden" name="furnitureID" value="<?php echo htmlspecialchars($_GET['id'] ?? ''); ?>"> 
            <div class="form-group">
                <label for="name">Product Name: *</label>
                <input type="text" id="name" name="name" 
                    value="<?php echo htmlspecialchars($product->name ?? ''); ?>" required>

            </div>
            
            <div class="form-group">
                <label for="price">Price: *</label>
                <input type="number" id="price" name="price" min="0.01" step="0.01" 
                    value="<?php echo htmlspecialchars($product->price ?? ''); ?>" required>
            </div>
            
            <div class="form-group">
                <label for="quantity">Quantity: *</label>
                <input type="number" id="quantity" name="quantity" min="0" 
                    value="<?php echo htmlspecialchars($product->stock_quantity ?? ''); ?>" required>

            </div>
            
            <div class="form-group">
                <label for="description">Description:</label>
                <textarea id="description" name="description"><?php 
                    echo htmlspecialchars($product->description ?? ''); ?></textarea>
            </div>
            
            <div class="form-group">
                <label for="category">Category: *</label>
                <select id="category" name="category" required>
                    <option value="">-- Select Category --</option>
                    <option value="Sofa" <?php if(($product->category ?? '') == 'Sofa') echo 'selected'; ?>>Sofa</option>
                    <option value="Chair" <?php if(($product->category ?? '') == 'Chair') echo 'selected'; ?>>Chair</option>
                    <option value="Table" <?php if(($product->category ?? '') == 'Table') echo 'selected'; ?>>Table</option>
                    <option value="Bed" <?php if(($product->category ?? '') == 'Bed') echo 'selected'; ?>>Bed</option>
                    <option value="Cabinet" <?php if(($product->category ?? '') == 'Cabinet') echo 'selected'; ?>>Cabinet</option>
                    <option value="Other" <?php if(($product->category ?? '') == 'Other') echo 'selected'; ?>>Other</option>
                </select>
            </div>
            
            <button type="submit" class="btn-submit">Update Product</button>
            <a href="AdminManageProduct.php" class="btn-cancel">Cancel</a>
        </form>
    </div>
</body>
</html>