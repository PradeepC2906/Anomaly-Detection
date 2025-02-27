import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras import backend as K
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Lambda, Layer, Dropout, GaussianNoise, LSTM, RepeatVector, TimeDistributed, Attention, Flatten, Reshape
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping
import matplotlib.pyplot as plt
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report
df = pd.read_csv('/content/drive/MyDrive/Car Hacking dataset/CICIoV2024.csv')
normal_data = df[df['specific_class'] == 'BENIGN']
features = ['ID', 'DATA_0', 'DATA_1', 'DATA_2', 'DATA_3', 'DATA_4', 'DATA_5', 'DATA_6', 'DATA_7']
X = normal_data[features].values
scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X)
X_scaled = X_scaled.reshape((X_scaled.shape[0], 1, X_scaled.shape[1]))
X_train, X_test = train_test_split(X_scaled, test_size=0.2, random_state=42)
latent_dim = 3
#Attention Layer
from tensorflow.keras import layers
class AttentionLayer(layers.Layer):
    def __init__(self, units):
        super(AttentionLayer, self).__init__()
        self.units = units

    def build(self, input_shape):
        self.W = self.add_weight(shape=(input_shape[-1], self.units),
                                 initializer='glorot_uniform', trainable=True)
        self.b = self.add_weight(shape=(self.units,), initializer='zeros', trainable=True)
        self.u = self.add_weight(shape=(self.units, 1), initializer='glorot_uniform', trainable=True)

    def call(self, inputs):
        score = K.tanh(K.dot(inputs, self.W) + self.b)
        attention_weights = K.softmax(K.dot(score, self.u), axis=1)
        context_vector = attention_weights * inputs
        context_vector = K.sum(context_vector, axis=1)
        return context_vector, attention_weights
# Encoder
input_data = Input(shape=(X_train.shape[1], X_train.shape[2]))
noisy_input = GaussianNoise(0.1)(input_data)
encoded_lstm = LSTM(64, activation='relu', return_sequences=True)(noisy_input)

# Attention Layer
attention_output, attention_weights = AttentionLayer(units=32)(encoded_lstm)
attention_output = Flatten()(attention_output)

attention_output = Dense(32, activation='relu')(attention_output)
attention_output = Dropout(0.3)(attention_output)
# Latent space (mean and log variance)
z_mean = Dense(latent_dim)(attention_output)
z_log_var = Dense(latent_dim)(attention_output)

# Sampling function
def sampling(args):
    z_mean, z_log_var = args
    epsilon = K.random_normal(shape=(K.shape(z_mean)[0], latent_dim), mean=0., stddev=1.)
    return z_mean + K.exp(0.5 * z_log_var) * epsilon

# Sampling layer
z = Lambda(sampling, output_shape=(latent_dim,))([z_mean, z_log_var])
# Decoder
decoded = Dense(32, activation='relu')(z)
decoded = Dropout(0.3)(decoded)
decoded = RepeatVector(X_train.shape[1])(decoded)


decoded = Reshape((X_train.shape[1], 32))(decoded)

decoded = LSTM(64, activation='relu', return_sequences=True)(decoded)
decoded = layers.TimeDistributed(Dense(X_train.shape[2], activation='sigmoid'))(decoded)
# VAE model
vae = Model(input_data, decoded)

class KLLossLayer(Layer):
    def call(self, inputs):
        z_mean, z_log_var = inputs
        kl_loss = -0.5 * K.sum(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis=-1)
        self.add_loss(K.mean(kl_loss))
        return inputs

[z_mean, z_log_var] = KLLossLayer()([z_mean, z_log_var])


def vae_loss(input_data, decoded):
    reconstruction_loss = K.mean(K.square(input_data - decoded))  # MSE loss for reconstruction
    return reconstruction_loss

# Compile the model
vae.compile(optimizer=Adam(), loss=vae_loss)

early_stopping = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
 history = vae.fit(X_train, X_train, epochs=20, batch_size=64, shuffle=True,
                  validation_data=(X_test, X_test), callbacks=[early_stopping])
# Plotting the loss curves
plt.figure(figsize=(6, 4))

# Training loss
plt.plot(history.history['loss'], label='Training Loss')

# Validation loss
plt.plot(history.history['val_loss'], label='Validation Loss')

# Adding titles and labels
plt.title('VAE Training and Validation Loss')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()
plt.grid(True)
plt.show()
# Check reconstruction from normal data
reconstructed_data = vae.predict(X_test)

# Reshape the reconstructed data to original shape for comparison
X_test_flat = X_test.reshape((X_test.shape[0], X_test.shape[2]))
reconstructed_data_flat = reconstructed_data.reshape((reconstructed_data.shape[0], reconstructed_data.shape[2]))

# Calculate reconstruction loss
reconstruction_loss = np.mean(np.square(X_test_flat - reconstructed_data_flat), axis=1)
 print(reconstruction_loss)
threshold = np.percentile(reconstruction_loss, 90)
print(f"Threshold for anomaly detection: {threshold}")
attack_data = df[df['specific_class'] != 'BENIGN']
# Prepare your attack data
X_attack = attack_data[features].values

# Normalize the attack data
X_attack_scaled = scaler.transform(X_attack)
X_attack_scaled = X_attack_scaled.reshape((X_attack_scaled.shape[0], 1, X_attack_scaled.shape[1]))

# Predict reconstruction for attack data
attack_reconstructed = vae.predict(X_attack_scaled)
# Reshape attack data for comparison
X_attack_flat = X_attack_scaled.reshape((X_attack_scaled.shape[0], X_attack_scaled.shape[2]))
attack_reconstructed_flat = attack_reconstructed.reshape((attack_reconstructed.shape[0], attack_reconstructed.shape[2]))

# Calculate reconstruction loss for attack data
attack_reconstruction_loss = np.mean(np.square(X_attack_flat - attack_reconstructed_flat), axis=1)

# Classify attacks based on reconstruction loss
attack_predictions = (attack_reconstruction_loss > threshold).astype(int)
# Load normal data for evaluation
normal_data = df[df['specific_class'] == 'BENIGN']
X_normal = normal_data[features].values

# Normalize and reshape normal data for VAE input
X_normal_scaled = scaler.transform(X_normal)
X_normal_scaled = X_normal_scaled.reshape((X_normal_scaled.shape[0], 1, X_normal_scaled.shape[1]))

# Calculate reconstruction loss for normal data
normal_reconstructed = vae.predict(X_normal_scaled)
normal_reconstructed_flat = normal_reconstructed.reshape((normal_reconstructed.shape[0], normal_reconstructed.shape[2]))
normal_reconstruction_loss = np.mean(np.square(X_normal_scaled.reshape((X_normal_scaled.shape[0], X_normal_scaled.shape[2])) - normal_reconstructed_flat), axis=1)
y_true = np.ones(len(attack_predictions))
y_true_normal = np.zeros(len(normal_reconstruction_loss))

# Concatenate predictions and true labels for normal and attack data
y_true_combined = np.concatenate([y_true, y_true_normal])
combined_predictions = np.concatenate([attack_predictions, np.zeros(len(y_true_normal))])
# Evaluate the model
precision = precision_score(y_true_combined, combined_predictions, average='binary', zero_division=0)
recall = recall_score(y_true_combined, combined_predictions, average='binary', zero_division=0)
f1 = f1_score(y_true_combined, combined_predictions, average='binary', zero_division=0)

# Print the classification report
report = classification_report(y_true_combined, combined_predictions, target_names=['Normal', 'Anomaly'])
print("Precision:", precision)
print("Recall:", recall)
print("F1 Score:", f1)
print("Classification Report:\n", report)
from sklearn.metrics import confusion_matrix
import seaborn as sns
# Confusion matrix
cm = confusion_matrix(y_true_combined, combined_predictions)
print("Confusion Matrix:\n", cm)

# Plot the confusion matrix
plt.figure(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=['Normal', 'Anomaly'], yticklabels=['Normal', 'Anomaly'])
plt.ylabel('True Label')
plt.xlabel('Predicted Label')
plt.title('Confusion Matrix')
plt.show()
